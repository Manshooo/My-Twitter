import json
import shutil
import tempfile
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image as PILImage

from azzb.testing import ACTIVE

from .media import process_post_image
from .models import Image, Post

User = get_user_model()
MEDIA_ROOT = tempfile.mkdtemp(prefix='azzb-test-media-')


def tearDownModule():
	shutil.rmtree(MEDIA_ROOT, ignore_errors=True)


def make_upload(name='photo.jpg', size=(64, 48), fmt='JPEG', color=(200, 40, 40), **save_kwargs):
	buffer = BytesIO()
	PILImage.new('RGB', size, color).save(buffer, fmt, **save_kwargs)
	content_type = {'JPEG': 'image/jpeg', 'PNG': 'image/png', 'GIF': 'image/gif'}.get(fmt, 'application/octet-stream')
	return SimpleUploadedFile(name, buffer.getvalue(), content_type=content_type)


def exif_with_gps():
	exif = PILImage.Exif()
	exif[0x0110] = 'Secret Phone 9'  # модель камеры
	exif[0x0112] = 6  # повёрнуто на 90 градусов
	gps = exif.get_ifd(0x8825)
	gps[2] = (55.0, 45.0, 0.0)  # широта
	gps[4] = (37.0, 37.0, 0.0)  # долгота
	return exif


class ProcessImageTests(TestCase):
	def test_result_is_webp_without_exif_and_rotated(self):
		upload = make_upload(size=(80, 40), exif=exif_with_gps().tobytes())
		self.assertIn(b'Secret Phone', upload.read())
		result = process_post_image(upload)
		data = result.content.read()
		saved = PILImage.open(BytesIO(data))
		self.assertEqual(saved.format, 'WEBP')
		self.assertNotIn('exif', saved.info)
		self.assertNotIn(b'Secret Phone', data)
		# Ориентация 6 — фото повёрнуто, после обработки оно «стоит» правильно.
		self.assertEqual((result.width, result.height), (40, 80))

	def test_huge_resolution_rejected_before_decoding(self):
		# PNG 8000×8000 жмётся в несколько килобайт, а распакованный занял бы 256 МБ.
		with self.assertRaises(ValidationError):
			process_post_image(make_upload('bomb.png', size=(8000, 8000), fmt='PNG'))


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class CreatePostWithImagesTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user('alice', 'alice@example.com', 'pass-12345', **ACTIVE)
		self.client.force_login(self.user)

	def post(self, **data):
		return self.client.post('/api/new-post/', data)

	def test_bad_file_rejects_whole_post(self):
		bad = SimpleUploadedFile('bad.jpg', b'not an image', content_type='image/jpeg')
		response = self.post(text='x', images=[make_upload(), bad])
		self.assertEqual(response.status_code, 400)
		self.assertIn('bad.jpg', ' '.join(response.json()['errors']))
		self.assertFalse(Post.objects.exists())
		self.assertFalse(Image.objects.exists())


class RepliesTests(TestCase):
	def setUp(self):
		self.alice = User.objects.create_user('alice', 'alice@example.com', 'pass-12345', **ACTIVE)
		self.bob = User.objects.create_user('bob', 'bob@example.com', 'pass-12345', **ACTIVE)
		self.root = Post.objects.create(author=self.alice.profile, text='Корень ветки')
		self.client.force_login(self.bob)

	def reply(self, user, parent, text):
		self.client.force_login(user)
		return self.client.post('/api/new-post/', {'text': text, 'reply_to': str(parent.pk)})

	def test_reply_is_created_and_hidden_from_feeds(self):
		response = self.reply(self.bob, self.root, 'Ответ Боба')
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, f'В ответ <a href="/p/{self.root.pk}/">@alice</a>', html=False)
		reply = Post.objects.get(text='Ответ Боба')
		self.assertTrue(reply.is_reply)
		self.assertEqual(reply.reply_to, self.root)
		for sort in ('popular', 'new'):
			self.client.post('/settings/feed-sort/', {'sort': sort})
			self.assertNotContains(self.client.get('/'), 'Ответ Боба', msg_prefix=sort)
		self.assertNotContains(self.client.get('/users/bob/'), 'Ответ Боба')
		self.assertContains(self.client.get('/users/bob/?tab=replies'), 'Ответ Боба')

	def test_cannot_reply_to_hidden_or_missing_post(self):
		self.alice.is_active = False
		self.alice.save()
		self.assertEqual(self.reply(self.bob, self.root, 'x').status_code, 404)
		self.assertEqual(
			self.client.post('/api/new-post/', {'text': 'x', 'reply_to': 'garbage'}).status_code, 400,
		)
		self.assertFalse(Post.objects.filter(text='x').exists())

	def test_unavailable_reply_is_counted_and_shown_as_placeholder(self):
		self.reply(self.bob, self.root, 'Скрытый ответ')
		self.bob.is_active = False
		self.bob.save()
		self.client.force_login(self.alice)
		self.assertContains(self.client.get('/'), 'data-reply-count data-n="1">1<')
		page = self.client.get(f'/p/{self.root.pk}/')
		self.assertContains(page, 'Пост недоступен')
		self.assertNotContains(page, 'Скрытый ответ')

	def test_deleted_post_leaves_feeds_but_stays_in_thread(self):
		self.reply(self.bob, self.root, 'Удалю потом')
		middle = Post.objects.get(text='Удалю потом')
		self.reply(self.alice, middle, 'Ответ под удалённым')
		self.client.force_login(self.bob)
		self.client.post(f'/p/{middle.pk}/delete/', headers={'HX-Request': 'true'})
		self.assertTrue(Post.objects.filter(pk=middle.pk).exists())  # хранится полгода (azzb/retention.py)
		self.assertNotContains(self.client.get('/users/bob/?tab=replies'), 'Удалю потом')
		page = self.client.get(f'/p/{self.root.pk}/')
		self.assertContains(page, 'Пост удалён')
		self.assertNotContains(page, 'Удалю потом')
		self.assertContains(self.client.get(f'/p/{middle.pk}/'), 'Ответ под удалённым', status_code=404)
		# Удалённый пост без ответов не нужен и заглушкой.
		self.reply(self.bob, self.root, 'Одинокий')
		lonely = Post.objects.get(text='Одинокий')
		self.client.post(f'/p/{lonely.pk}/delete/', headers={'HX-Request': 'true'})
		self.assertEqual(self.client.get(f'/p/{lonely.pk}/').status_code, 404)


class EditPostTests(TestCase):
	def setUp(self):
		self.alice = User.objects.create_user('alice', 'alice@example.com', 'pass-12345', **ACTIVE)
		self.bob = User.objects.create_user('bob', 'bob@example.com', 'pass-12345', **ACTIVE)
		self.post = Post.objects.create(author=self.alice.profile, text='Перавя версия')

	def edit(self, user, text, post=None):
		self.client.force_login(user)
		payload = {'id': str((post or self.post).pk), 'text': text}
		return self.client.post('/api/edit-post/', json.dumps(payload), content_type='application/json')

	def test_author_edits_and_old_text_is_kept(self):
		response = self.edit(self.alice, 'Первая версия')
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Первая версия')
		self.assertContains(response, '· изменено')
		self.post.refresh_from_db()
		self.assertEqual(self.post.text, 'Первая версия')
		self.assertIsNotNone(self.post.edited_at)
		self.edit(self.alice, 'Третья версия')
		history = list(self.post.revisions.order_by('replaced_at').values_list('text', flat=True))
		self.assertEqual(history, ['Перавя версия', 'Первая версия'])
		first, second = self.post.revisions.order_by('replaced_at')
		self.assertEqual(first.valid_from, self.post.created_at)
		# Вторая версия действовала с момента первой правки.
		self.assertGreater(second.valid_from, first.valid_from)

	def test_only_author_can_edit(self):
		response = self.edit(self.bob, 'Взлом')
		self.assertEqual(response.status_code, 403)
		self.post.refresh_from_db()
		self.assertEqual(self.post.text, 'Перавя версия')
		self.client.logout()
		response = self.client.post('/api/edit-post/', json.dumps({'id': str(self.post.pk), 'text': 'x'}), content_type='application/json')
		self.assertNotEqual(response.status_code, 200)

HTMX = {'HX-Request': 'true'}


class HtmxActionsTests(TestCase):
	"""Лайк, удаление и публикация через htmx."""

	def setUp(self):
		self.alice = User.objects.create_user('alice', 'alice@example.com', 'pass-12345', **ACTIVE)
		self.bob = User.objects.create_user('bob', 'bob@example.com', 'pass-12345', **ACTIVE)
		self.post = Post.objects.create(author=self.alice.profile, text='Пост Алисы')

	def test_like_returns_new_button(self):
		self.client.force_login(self.bob)
		url = f'/p/{self.post.pk}/like/'
		response = self.client.post(url, headers=HTMX)
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'aria-pressed="true"')
		self.assertContains(response, 'data-like-count data-n="1">1<')
		self.assertContains(response, f'hx-post="{url}"')
		response = self.client.post(url, headers=HTMX)
		self.assertContains(response, 'aria-pressed="false"')
		self.assertEqual(self.post.likes.count(), 0)

	def test_delete_main_post_redirects_home(self):
		self.client.force_login(self.alice)
		response = self.client.post(f'/p/{self.post.pk}/delete/', {'main': '1'}, headers=HTMX)
		self.assertEqual(response['HX-Redirect'], '/')

	def test_only_author_deletes(self):
		self.client.force_login(self.bob)
		self.assertEqual(self.client.post(f'/p/{self.post.pk}/delete/', headers=HTMX).status_code, 403)
		self.assertTrue(Post.objects.filter(pk=self.post.pk).exists())

	@override_settings(MEDIA_ROOT=MEDIA_ROOT)
	def test_compose_new_post_with_images(self):
		self.client.force_login(self.bob)
		response = self.client.post('/compose/', {
			'text': 'Через htmx', 'images': [make_upload()], 'alt': ['Описание'], 'reply_to': '', 'edit': '',
		}, headers=HTMX)
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Через htmx')
		self.assertContains(response, 'alt="Описание"')

	def test_compose_expired_session_is_401_not_login_page(self):
		response = self.client.post('/compose/', {'text': 'x'}, headers=HTMX)
		self.assertEqual(response.status_code, 401)
		self.assertFalse(Post.objects.filter(text='x').exists())

	def test_pages_load_htmx_and_send_csrf_header(self):
		self.client.force_login(self.bob)
		page = self.client.get('/')
		self.assertContains(page, 'vendor/htmx-2.0.4.min.js')
		self.assertContains(page, '<body hx-headers=')
		self.assertContains(page, '"X-CSRFToken": "')
