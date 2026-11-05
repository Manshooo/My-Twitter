import json
import shutil
import tempfile
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
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

	def test_deleting_post_deletes_files(self):
		self.post(text='x', images=[make_upload()])
		image = Image.objects.get()
		storage, name = image.file.storage, image.file.name
		self.assertTrue(storage.exists(name))
		with self.captureOnCommitCallbacks(execute=True):
			self.client.post('/api/delete-post/', json.dumps({'id': str(image.post_id)}), content_type='application/json')
		self.assertFalse(storage.exists(name))

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
		self.assertIn('data-reply-count>2<', page)

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
		more = self.client.get(next_url, headers={'X-Requested-With': 'azzb-load-more'})
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

	def test_reply_count_ignores_hidden_replies(self):
		self.reply(self.bob, self.root, 'Скрытый ответ')
		self.bob.is_active = False
		self.bob.save()
		self.client.force_login(self.alice)
		self.assertNotContains(self.client.get('/'), 'data-reply-count>1<')

	def test_feed_query_count_does_not_grow_with_replies(self):
		for i in range(5):
			post = Post.objects.create(author=self.alice.profile, text=f'пост {i}')
			Post.objects.create(author=self.bob.profile, text='ответ', reply_to=post, is_reply=True)
		self.client.force_login(self.bob)
		self.client.get('/')  # прогрев: сессия, last_visit
		# сессия, пользователь, профиль, посты, картинки, «Кого почитать» — сколько бы ни было ответов.
		with self.assertNumQueries(6):
			self.client.get('/')
