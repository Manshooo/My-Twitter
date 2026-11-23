from django.test import TestCase, override_settings

from azzb.testing import ACTIVE
from post.tests import MEDIA_ROOT, make_upload

from .models import CustomUser

# Сама модель, а не get_user_model(): так редактор знает про create_user и поля аккаунта.
User = CustomUser


class BlockTests(TestCase):
	"""Блокировка скрывает посты в обе стороны и снимает подписки."""

	def setUp(self):
		from post.models import Post
		self.alice = User.objects.create_user('alice', 'alice@example.com', 'pass-12345', **ACTIVE)
		self.bob = User.objects.create_user('bob', 'bob@example.com', 'pass-12345', **ACTIVE)
		self.alice_post = Post.objects.create(author=self.alice.profile, text='пост Алисы')
		self.bob_post = Post.objects.create(author=self.bob.profile, text='пост Боба')
		self.client.force_login(self.alice)

	def act(self, action, username='bob', **extra):
		return self.client.post(f'/users/{username}/', {action: '', **extra})

	def test_block_hides_posts_both_ways_and_removes_follows(self):
		from post.models import Post

		from .models import FollowThrough
		FollowThrough.objects.create(follower=self.alice.profile, followee=self.bob.profile)
		FollowThrough.objects.create(follower=self.bob.profile, followee=self.alice.profile)
		self.act('block')
		self.assertFalse(FollowThrough.objects.exists())
		self.assertNotIn(self.bob_post, Post.objects.visible_to(self.alice))
		self.assertNotIn(self.alice_post, Post.objects.visible_to(self.bob))
		self.assertIn(self.bob_post, Post.objects.visible_to(None))
		self.assertNotContains(self.client.get('/'), 'пост Боба')
		page = self.client.get(f'/p/{self.bob_post.pk}/')  # по прямой ссылке — заглушка
		self.assertContains(page, 'Пост недоступен', status_code=404)
		self.assertNotContains(page, 'пост Боба', status_code=404)

	def test_blocked_user_cannot_follow_like_or_reply(self):
		from .models import Block, FollowThrough
		Block.objects.create(blocker=self.alice.profile, blocked=self.bob.profile)
		self.client.force_login(self.bob)
		self.act('subscribe', username='alice')
		self.assertFalse(FollowThrough.objects.exists())
		self.assertEqual(self.client.post(f'/p/{self.alice_post.pk}/like/').status_code, 404)
		response = self.client.post('/compose/', {'text': 'ответ', 'reply_to': str(self.alice_post.pk)}, headers={'HX-Request': 'true'})
		self.assertEqual(response.status_code, 404)
		page = self.client.get('/users/alice/')
		self.assertContains(page, 'ограничил(а) доступ')
		self.assertNotContains(page, 'name="subscribe"')


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class AccountDataTests(TestCase):
	"""E6: выгрузка своих данных и удаление аккаунта."""

	def setUp(self):
		from post.models import Post
		self.alice = User.objects.create_user('alice', 'alice@example.com', 'pass-12345', **ACTIVE)
		self.bob = User.objects.create_user('bob', 'bob@example.com', 'pass-12345', **ACTIVE)
		self.post = Post.objects.create(author=self.alice.profile, text='мой пост')
		Post.objects.create(author=self.bob.profile, text='пост Боба')
		self.client.force_login(self.alice)

	def test_export_zip(self):
		import io
		import json
		import zipfile
		self.client.post('/compose/', {'text': 'с картинкой', 'images': make_upload()}, headers={'HX-Request': 'true'})
		self.assertEqual(self.client.get('/settings/account/').status_code, 200)
		response = self.client.post('/settings/account/export/')
		self.assertEqual(response.status_code, 200)
		self.assertIn('attachment', response['Content-Disposition'])
		bundle = zipfile.ZipFile(io.BytesIO(b''.join(response.streaming_content)))
		data = json.loads(bundle.read('data.json'))
		self.assertEqual(data['account']['email'], 'alice@example.com')
		texts = [post['text'] for post in data['posts']]
		self.assertIn('мой пост', texts)
		self.assertNotIn('пост Боба', texts)
		image = next(post for post in data['posts'] if post['images'])['images'][0]['file']
		self.assertIn(image, bundle.namelist())

	def test_delete_requires_password(self):
		response = self.client.post('/settings/account/delete/', {'confirm': 'wrong'})
		self.assertEqual(response.status_code, 400)
		self.assertContains(response, 'Неверный пароль', status_code=400)
		self.assertTrue(User.objects.filter(username='alice').exists())

	def test_delete_account(self):
		# Аккаунт сразу отключается и пропадает, а данные хранятся полгода (azzb/retention.py).
		from post.models import Post
		response = self.client.post('/settings/account/delete/', {'confirm': 'pass-12345'})
		self.assertRedirects(response, '/', fetch_redirect_response=False)
		self.assertNotIn('_auth_user_id', self.client.session)
		alice = User.objects.get(username='alice')
		self.assertFalse(alice.is_active)
		self.assertIsNotNone(alice.deleted_at)
		self.assertIsNotNone(Post.objects.get(text='мой пост').deleted_at)
		self.assertIsNone(Post.objects.get(text='пост Боба').deleted_at)
		self.client.force_login(User.objects.get(username='bob'))
		self.assertEqual(self.client.get('/users/alice/').status_code, 404)
		self.assertNotContains(self.client.get('/'), 'мой пост')
