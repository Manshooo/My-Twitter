import json
import shutil
import tempfile
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image as PILImage

from .media import MAX_SIDE, parse_crop, process_cropped_image, process_post_image
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

	def test_large_image_is_downscaled(self):
		result = process_post_image(make_upload(size=(MAX_SIDE * 2, 100)))
		self.assertEqual(result.width, MAX_SIDE)

	def test_png_with_transparency_keeps_alpha(self):
		buffer = BytesIO()
		PILImage.new('RGBA', (20, 20), (0, 0, 0, 0)).save(buffer, 'PNG')
		result = process_post_image(SimpleUploadedFile('a.png', buffer.getvalue(), content_type='image/png'))
		self.assertEqual(PILImage.open(BytesIO(result.content.read())).mode, 'RGBA')

	def test_animated_gif_stays_animated(self):
		buffer = BytesIO()
		frames = [PILImage.new('RGB', (30, 30), c) for c in ((255, 0, 0), (0, 255, 0), (0, 0, 255))]
		frames[0].save(buffer, 'GIF', save_all=True, append_images=frames[1:], duration=80, loop=0)
		result = process_post_image(SimpleUploadedFile('a.gif', buffer.getvalue(), content_type='image/gif'))
		saved = PILImage.open(BytesIO(result.content.read()))
		self.assertEqual(saved.n_frames, 3)

	def test_not_an_image_rejected(self):
		fake = SimpleUploadedFile('evil.jpg', b'<script>alert(1)</script>', content_type='image/jpeg')
		with self.assertRaises(ValidationError):
			process_post_image(fake)

	def test_unsupported_format_rejected(self):
		with self.assertRaises(ValidationError):
			process_post_image(make_upload('a.bmp', fmt='BMP'))

	def test_huge_resolution_rejected_before_decoding(self):
		# PNG 8000×8000 жмётся в несколько килобайт, а распакованный занял бы 256 МБ.
		with self.assertRaises(ValidationError):
			process_post_image(make_upload('bomb.png', size=(8000, 8000), fmt='PNG'))

	def test_crop_and_resize(self):
		result = process_cropped_image(make_upload(size=(1000, 500)), (400, 400), parse_crop('0.5,0,0.5,1'))
		self.assertEqual((result.width, result.height), (400, 400))
		# Без области — центр нужных пропорций; маленькую картинку не растягиваем.
		small = process_cropped_image(make_upload(size=(300, 300)), (1500, 500))
		self.assertEqual((small.width, small.height), (300, 100))

	def test_parse_crop_rejects_garbage(self):
		for value in ('', 'a,b,c,d', '0,0,0,1', '-0.1,0,1,1', '0.5,0,0.8,1', '1,1,1'):
			self.assertIsNone(parse_crop(value), value)


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class CreatePostWithImagesTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user('alice', 'alice@example.com', 'pass-12345')
		self.client.force_login(self.user)

	def post(self, **data):
		return self.client.post('/api/new-post/', data)

	def test_images_saved_in_order_with_alt(self):
		response = self.post(
			text='С картинками',
			images=[make_upload('1.jpg'), make_upload('2.png', fmt='PNG')],
			alt=['Кот на окне', ''],
		)
		self.assertEqual(response.status_code, 200)
		post = Post.objects.get()
		images = list(post.images.all())
		self.assertEqual([image.alt for image in images], ['Кот на окне', ''])
		self.assertTrue(all(image.file.name.endswith('.webp') for image in images))
		self.assertTrue(images[0].file.name.startswith('posts/'))
		self.assertEqual((images[0].width, images[0].height), (64, 48))
		self.assertContains(response, 'alt="Кот на окне"')
		self.assertContains(response, 'Картинка 2 без описания')
		self.assertContains(response, 'data-lightbox="1"')

	def test_image_without_text_is_allowed(self):
		self.assertEqual(self.post(images=[make_upload()]).status_code, 200)
		self.assertEqual(Post.objects.get().text, '')

	def test_more_than_four_images_rejected(self):
		response = self.post(text='x', images=[make_upload(f'{i}.jpg') for i in range(5)])
		self.assertEqual(response.status_code, 400)
		self.assertFalse(Post.objects.exists())

	def test_bad_file_rejects_whole_post(self):
		bad = SimpleUploadedFile('bad.jpg', b'not an image', content_type='image/jpeg')
		response = self.post(text='x', images=[make_upload(), bad])
		self.assertEqual(response.status_code, 400)
		self.assertIn('bad.jpg', ' '.join(response.json()['errors']))
		self.assertFalse(Post.objects.exists())
		self.assertFalse(Image.objects.exists())

	def test_deleted_post_keeps_files_until_purged(self):
		from .services import purge_posts
		self.post(text='x', images=[make_upload()])
		image = Image.objects.get()
		storage, name = image.file.storage, image.file.name
		with self.captureOnCommitCallbacks(execute=True):
			self.client.post('/api/delete-post/', json.dumps({'id': str(image.post_id)}), content_type='application/json')
		self.assertTrue(storage.exists(name))  # хранится полгода (azzb/retention.py)
		with self.captureOnCommitCallbacks(execute=True):
			purge_posts(Post.objects.filter(pk=image.post_id))
		self.assertFalse(storage.exists(name))
		self.assertEqual(Post.objects.get(pk=image.post_id).text, '')

	def test_media_tab_and_feed_show_images(self):
		self.post(text='x', images=[make_upload()])
		self.assertContains(self.client.get('/users/alice/?tab=media'), 'data-gallery')
		self.assertContains(self.client.get('/'), 'class="media media-1"')


class RepliesTests(TestCase):
	def setUp(self):
		self.alice = User.objects.create_user('alice', 'alice@example.com', 'pass-12345')
		self.bob = User.objects.create_user('bob', 'bob@example.com', 'pass-12345')
		self.root = Post.objects.create(author=self.alice.profile, text='Корень ветки')

	def reply(self, user, parent, text):
		self.client.force_login(user)
		return self.client.post('/api/new-post/', {'text': text, 'reply_to': str(parent.pk)})

	def test_reply_is_created_and_hidden_from_feeds(self):
		response = self.reply(self.bob, self.root, 'Ответ Боба')
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'В ответ <a href="/p/%s/">@alice</a>' % self.root.pk, html=False)
		reply = Post.objects.get(text='Ответ Боба')
		self.assertTrue(reply.is_reply)
		self.assertEqual(reply.reply_to, self.root)
		for url in ('/', '/hot/'):
			self.assertNotContains(self.client.get(url), 'Ответ Боба')
		self.assertNotContains(self.client.get('/users/bob/'), 'Ответ Боба')
		self.assertContains(self.client.get('/users/bob/?tab=replies'), 'Ответ Боба')

	def test_thread_page_shows_ancestors_and_replies_in_order(self):
		self.reply(self.bob, self.root, 'Первый ответ')
		first = Post.objects.get(text='Первый ответ')
		self.reply(self.alice, first, 'Ответ на ответ')
		self.reply(self.alice, self.root, 'Второй ответ')

		page = self.client.get(f'/p/{self.root.pk}/').content.decode()
		page = page[page.index('<main'):]
		self.assertLess(page.index('Первый ответ'), page.index('Второй ответ'))
		self.assertNotIn('Ответ на ответ', page)  # только прямые ответы
		self.assertIn('data-reply-count>3<', page)  # счётчик — вся ветка, с ответом на ответ

		nested = Post.objects.get(text='Ответ на ответ')
		page = self.client.get(f'/p/{nested.pk}/').content.decode()
		page = page[page.index('<main'):]  # в <title> тоже есть текст поста
		self.assertLess(page.index('Корень ветки'), page.index('Первый ответ'))
		self.assertLess(page.index('Первый ответ'), page.index('Ответ на ответ'))
		self.assertIn('post-parent', page)

	def test_replies_paginate_oldest_first(self):
		from .pagination import PAGE_SIZE
		for i in range(PAGE_SIZE + 3):
			Post.objects.create(author=self.bob.profile, text=f'ответ №{i:02d}', reply_to=self.root, is_reply=True)
		page = self.client.get(f'/p/{self.root.pk}/')
		self.assertContains(page, 'ответ №00')
		self.assertNotContains(page, f'ответ №{PAGE_SIZE:02d}')
		next_url = page.context['next_url']
		more = self.client.get(next_url, headers={'HX-Request': 'true'})
		self.assertContains(more, f'ответ №{PAGE_SIZE + 2:02d}')
		self.assertNotContains(more, 'ответ №00')

	def test_deleting_parent_keeps_reply_out_of_feeds(self):
		self.reply(self.bob, self.root, 'Сирота')
		self.root.delete()
		orphan = Post.objects.get(text='Сирота')
		self.assertIsNone(orphan.reply_to)
		self.assertNotContains(self.client.get('/'), 'Сирота')
		self.assertContains(self.client.get(f'/p/{orphan.pk}/'), 'Начало ветки удалено')

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
		self.assertContains(self.client.get('/'), 'data-reply-count>1<')
		page = self.client.get(f'/p/{self.root.pk}/')
		self.assertContains(page, 'Пост недоступен')
		self.assertNotContains(page, 'Скрытый ответ')

	def test_reply_counter_follows_the_chain(self):
		self.reply(self.bob, self.root, 'Первый')
		first = Post.objects.get(text='Первый')
		self.reply(self.alice, first, 'Второй')
		second = Post.objects.get(text='Второй')
		self.root.refresh_from_db()
		first.refresh_from_db()
		self.assertEqual((self.root.replies_count, first.replies_count), (2, 1))
		self.client.post(f'/p/{second.pk}/delete/', headers={'HX-Request': 'true'})
		self.root.refresh_from_db()
		first.refresh_from_db()
		self.assertEqual((self.root.replies_count, first.replies_count), (1, 0))

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
		self.assertContains(self.client.get(f'/p/{middle.pk}/'), 'Ответ под удалённым')
		# Удалённый пост без ответов не нужен и заглушкой.
		self.reply(self.bob, self.root, 'Одинокий')
		lonely = Post.objects.get(text='Одинокий')
		self.client.post(f'/p/{lonely.pk}/delete/', headers={'HX-Request': 'true'})
		self.assertEqual(self.client.get(f'/p/{lonely.pk}/').status_code, 404)

	def test_cannot_like_or_reply_to_deleted_post(self):
		from .services import delete_post
		delete_post(self.root)
		self.client.force_login(self.bob)
		self.assertEqual(self.client.post(f'/p/{self.root.pk}/like/', headers={'HX-Request': 'true'}).status_code, 404)
		self.assertEqual(self.reply(self.bob, self.root, 'поздно').status_code, 404)

	def chat(self, start, authors):
		"""Переписка под start: каждый следующий пост — ответ на предыдущий."""
		posts, parent = [], start
		for i, user in enumerate(authors):
			parent = Post.objects.create(author=user.profile, text=f'реплика {i}', reply_to=parent, is_reply=True)
			posts.append(parent)
		Post.objects.filter(pk__in=[start.pk] + [p.pk for p in posts]).update(replies_count=0)
		for i, post in enumerate([start] + posts):
			Post.objects.filter(pk=post.pk).update(replies_count=len(posts) - i)
		return posts

	@staticmethod
	def main_part(response):
		page = response.content.decode()
		return page[page.index('<main'):]

	def test_single_reply_unfolds_whole_conversation(self):
		self.chat(self.root, [self.bob, self.alice] * 4)
		page = self.main_part(self.client.get(f'/p/{self.root.pk}/'))
		positions = [page.index(f'реплика {i}<') for i in range(8)]
		self.assertEqual(positions, sorted(positions))
		self.assertIn('post-chain', page)
		self.assertNotIn('Показать продолжение', page)

	def test_long_conversation_continues_by_button(self):
		from .views import CONVERSATION_PAGE
		posts = self.chat(self.root, [self.bob, self.alice] * CONVERSATION_PAGE)
		page = self.main_part(self.client.get(f'/p/{self.root.pk}/'))
		# Первый ответ — в списке, под ним CONVERSATION_PAGE сообщений разговора.
		self.assertIn(f'реплика {CONVERSATION_PAGE}<', page)
		self.assertNotIn(f'реплика {CONVERSATION_PAGE + 1}<', page)
		last = posts[CONVERSATION_PAGE]
		self.assertIn(f'/p/{last.pk}/conversation/?more=1', page)
		more = self.client.get(f'/p/{last.pk}/conversation/?more=1', headers={'HX-Request': 'true'}).content.decode()
		self.assertIn(f'реплика {CONVERSATION_PAGE + 1}<', more)
		self.assertNotIn(f'реплика {CONVERSATION_PAGE}<', more)
		# Без htmx — просто страница поста.
		self.assertRedirects(self.client.get(f'/p/{last.pk}/conversation/'), f'/p/{last.pk}/')

	def test_conversation_follows_the_dialogue_at_forks(self):
		first, second = self.chat(self.root, [self.bob, self.alice])
		carol = User.objects.create_user('carol', 'carol@example.com', 'pass-12345')
		# На «реплику 1» (Алиса) отвечают Кэрол (раньше) и Боб — продолжением разговора будет Боб.
		Post.objects.create(author=carol.profile, text='вставка Кэрол', reply_to=second, is_reply=True)
		Post.objects.create(author=self.bob.profile, text='Боб отвечает Алисе', reply_to=second, is_reply=True)
		page = self.main_part(self.client.get(f'/p/{self.root.pk}/'))
		self.assertIn('Боб отвечает Алисе', page)
		self.assertNotIn('вставка Кэрол', page)
		self.assertIn('Ещё 1 ответ на этот пост', page)
		# Если подходящего ответа нет — линия обрывается ссылкой на все ответы.
		Post.objects.filter(text='Боб отвечает Алисе').update(author=carol.profile)
		page = self.main_part(self.client.get(f'/p/{self.root.pk}/'))
		self.assertNotIn('Боб отвечает Алисе', page)
		self.assertIn('Ещё 2 ответа на этот пост', page)

	def test_several_replies_get_a_button_instead_of_unfolding(self):
		first, _ = self.chat(self.root, [self.bob, self.alice])
		Post.objects.create(author=self.alice.profile, text='Другой ответ', reply_to=self.root, is_reply=True)
		page = self.main_part(self.client.get(f'/p/{self.root.pk}/'))
		self.assertNotIn('реплика 1<', page)
		self.assertIn(f'/p/{first.pk}/conversation/', page)
		self.assertIn('Показать ветку · 1 ответ', page)
		part = self.client.get(f'/p/{first.pk}/conversation/', headers={'HX-Request': 'true'})
		self.assertContains(part, 'реплика 1<', html=False)

	def test_conversation_shows_unavailable_posts_as_placeholders(self):
		self.chat(self.root, [self.bob, self.alice, self.bob])
		Post.objects.filter(text='реплика 1').update(hidden_at=timezone.now(), hidden_reason='спам')
		page = self.main_part(self.client.get(f'/p/{self.root.pk}/'))
		self.assertIn('Пост скрыт модератором', page)
		self.assertIn('реплика 2<', page)


class EditPostTests(TestCase):
	def setUp(self):
		self.alice = User.objects.create_user('alice', 'alice@example.com', 'pass-12345')
		self.bob = User.objects.create_user('bob', 'bob@example.com', 'pass-12345')
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

	def test_same_text_is_not_a_revision(self):
		self.edit(self.alice, '  Перавя версия  ')
		self.post.refresh_from_db()
		self.assertIsNone(self.post.edited_at)
		self.assertFalse(self.post.revisions.exists())

	def test_only_author_can_edit(self):
		response = self.edit(self.bob, 'Взлом')
		self.assertEqual(response.status_code, 403)
		self.post.refresh_from_db()
		self.assertEqual(self.post.text, 'Перавя версия')
		self.client.logout()
		response = self.client.post('/api/edit-post/', json.dumps({'id': str(self.post.pk), 'text': 'x'}), content_type='application/json')
		self.assertNotEqual(response.status_code, 200)

	def test_limits(self):
		self.assertEqual(self.edit(self.alice, '').status_code, 400)
		self.assertEqual(self.edit(self.alice, 'x' * 501).status_code, 400)
		self.assertEqual(self.edit(self.alice, None).status_code, 400)
		self.post.refresh_from_db()
		self.assertEqual(self.post.text, 'Перавя версия')

	@override_settings(MEDIA_ROOT=MEDIA_ROOT)
	def test_post_with_images_can_lose_its_text(self):
		self.client.force_login(self.alice)
		self.client.post('/api/new-post/', {'text': 'С картинкой', 'images': [make_upload()]})
		with_image = Post.objects.get(text='С картинкой')
		self.assertEqual(self.edit(self.alice, '', post=with_image).status_code, 200)
		with_image.refresh_from_db()
		self.assertEqual(with_image.text, '')
		self.assertEqual(with_image.images.count(), 1)

	def test_edit_menu_only_for_author(self):
		self.client.force_login(self.alice)
		self.assertContains(self.client.get('/'), 'role="menuitem" data-edit')
		self.client.force_login(self.bob)
		self.assertNotContains(self.client.get('/'), 'role="menuitem" data-edit')


HTMX = {'HX-Request': 'true'}


class HtmxActionsTests(TestCase):
	"""Действия на страницах через htmx: лайк, удаление, composer, подгрузка лент."""

	def setUp(self):
		self.alice = User.objects.create_user('alice', 'alice@example.com', 'pass-12345')
		self.bob = User.objects.create_user('bob', 'bob@example.com', 'pass-12345')
		self.post = Post.objects.create(author=self.alice.profile, text='Пост Алисы')

	def test_like_returns_new_button(self):
		self.client.force_login(self.bob)
		url = f'/p/{self.post.pk}/like/'
		response = self.client.post(url, headers=HTMX)
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'aria-pressed="true"')
		self.assertContains(response, 'data-like-count>1<')
		self.assertContains(response, f'hx-post="{url}"')
		response = self.client.post(url, headers=HTMX)
		self.assertContains(response, 'aria-pressed="false"')
		self.assertEqual(self.post.likes.count(), 0)

	def test_like_needs_login_and_post(self):
		url = f'/p/{self.post.pk}/like/'
		response = self.client.post(url, headers=HTMX)
		self.assertEqual(response.status_code, 401)
		self.assertIn('errors', response.json())
		self.assertEqual(self.client.post(url).status_code, 302)  # без htmx — на страницу входа
		self.client.force_login(self.bob)
		self.assertEqual(self.client.get(url).status_code, 405)

	def test_cannot_like_hidden_post(self):
		self.alice.is_active = False
		self.alice.save()
		self.client.force_login(self.bob)
		self.assertEqual(self.client.post(f'/p/{self.post.pk}/like/', headers=HTMX).status_code, 404)

	def test_delete_triggers_event_with_parent(self):
		reply = Post.objects.create(author=self.bob.profile, text='ответ', reply_to=self.post, is_reply=True)
		self.client.force_login(self.bob)
		response = self.client.post(f'/p/{reply.pk}/delete/', headers=HTMX)
		self.assertEqual(response.status_code, 200)
		events = json.loads(response['HX-Trigger'])
		self.assertEqual(list(events), ['azzb:toast', 'azzb:post-deleted'])  # тост до удаления карточки
		self.assertEqual(events['azzb:post-deleted'], {'id': str(reply.pk), 'replyOf': str(self.post.pk)})
		self.assertEqual(events['azzb:toast'], 'Пост удалён')
		self.assertIsNotNone(Post.objects.get(pk=reply.pk).deleted_at)

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

	def test_compose_reply_and_errors(self):
		self.client.force_login(self.bob)
		response = self.client.post('/compose/', {'text': 'Ответ', 'reply_to': str(self.post.pk)}, headers=HTMX)
		self.assertContains(response, 'В ответ')
		self.assertTrue(Post.objects.get(text='Ответ').is_reply)
		response = self.client.post('/compose/', {'text': '  '}, headers=HTMX)
		self.assertEqual(response.status_code, 400)
		self.assertIn('errors', response.json())
		response = self.client.post('/compose/', {'text': 'x', 'reply_to': '00000000-0000-0000-0000-000000000000'}, headers=HTMX)
		self.assertEqual(response.status_code, 404)

	def test_compose_edit_own_only(self):
		self.client.force_login(self.bob)
		response = self.client.post('/compose/', {'text': 'Взлом', 'edit': str(self.post.pk)}, headers=HTMX)
		self.assertEqual(response.status_code, 403)
		self.client.force_login(self.alice)
		response = self.client.post('/compose/', {'text': 'Исправлено', 'edit': str(self.post.pk)}, headers=HTMX)
		self.assertContains(response, 'Исправлено')
		self.assertContains(response, '· изменено')
		self.assertEqual(self.client.post('/compose/', {'text': 'x', 'edit': 'мусор'}, headers=HTMX).status_code, 400)

	def test_compose_expired_session_is_401_not_login_page(self):
		response = self.client.post('/compose/', {'text': 'x'}, headers=HTMX)
		self.assertEqual(response.status_code, 401)
		self.assertFalse(Post.objects.filter(text='x').exists())

	def test_feed_page_vs_htmx_portion(self):
		from .pagination import PAGE_SIZE
		for i in range(PAGE_SIZE + 1):
			Post.objects.create(author=self.alice.profile, text=f'пост {i}')
		page = self.client.get('/')
		self.assertContains(page, '<html')
		self.assertIn('HX-Request', page['Vary'])
		self.assertContains(page, 'hx-trigger="click, revealed"')
		portion = self.client.get(page.context['next_url'], headers=HTMX)
		self.assertNotContains(portion, '<html')
		self.assertContains(portion, 'data-post-id')

	def test_pages_load_htmx_and_send_csrf_header(self):
		self.client.force_login(self.bob)
		page = self.client.get('/')
		self.assertContains(page, 'vendor/htmx-2.0.4.min.js')
		self.assertContains(page, '<body hx-headers=')
		self.assertContains(page, '"X-CSRFToken": "')


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class PageChromeTests(TestCase):
	"""Превью ссылок (og:image) и скелетоны подгрузки ленты (C4, C6)."""

	def setUp(self):
		self.alice = User.objects.create_user('alice', 'alice@example.com', 'pass-12345')

	def test_post_page_og_image(self):
		plain = Post.objects.create(author=self.alice.profile, text='Без картинки')
		response = self.client.get(f'/p/{plain.pk}/')
		self.assertContains(response, 'og-default.png', count=1)
		self.assertContains(response, 'property="og:image"', count=1)
		self.assertContains(response, 'property="og:site_name"', count=1)
		self.client.force_login(self.alice)
		self.client.post('/compose/', {'text': 'С фото', 'images': [make_upload()]}, headers=HTMX)
		with_photo = Post.objects.get(text='С фото')
		response = self.client.get(f'/p/{with_photo.pk}/')
		self.assertNotContains(response, 'og-default.png')
		self.assertContains(response, 'property="og:image"', count=1)
		self.assertContains(response, with_photo.images.first().file.url)

	def test_load_more_has_skeletons(self):
		from .pagination import PAGE_SIZE
		for i in range(PAGE_SIZE + 1):
			Post.objects.create(author=self.alice.profile, text=f'Пост {i}')
		response = self.client.get('/')
		self.assertContains(response, 'class="skel-cards"', count=1)
		self.assertContains(response, 'hx-target="closest .load-more"')
		self.assertContains(response, 'hx-indicator="closest .load-more"')
		self.assertNotContains(response, "{#")

	def test_templates_have_no_multiline_hash_comments(self):
		# {# … #} в Django только однострочный: многострочный попадает на страницу как текст.
		import re
		from pathlib import Path

		from django.conf import settings
		root = Path(settings.BASE_DIR)
		bad = [
			str(path.relative_to(root)) for app in ('azzb', 'post', 'accounts', 'moderation', 'api')
			for path in (root / app).rglob('*.html')
			if re.search(r'\{#(?:(?!#\}).)*\n', path.read_text(encoding='utf-8'), flags=re.S)
		]
		self.assertEqual(bad, [])
