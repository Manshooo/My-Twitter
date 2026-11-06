import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from post.models import Post

User = get_user_model()


class ProfileApiPermissionsTests(TestCase):
	def setUp(self):
		self.owner = User.objects.create_user('owner', 'owner@example.com', 'pass-12345')
		self.other = User.objects.create_user('other', 'other@example.com', 'pass-12345')
		self.url = f'/api/profiles/{self.owner.profile.pk}/'

	def test_anonymous_cannot_read_update_or_delete(self):
		self.assertEqual(self.client.get(self.url).status_code, 403)
		self.assertEqual(self.client.put(self.url, {'bio': 'x'}, content_type='application/json').status_code, 403)
		self.assertEqual(self.client.delete(self.url).status_code, 403)
		self.assertTrue(User.objects.filter(pk=self.owner.pk).exists())

	def test_anonymous_cannot_list_profiles(self):
		self.assertEqual(self.client.get('/api/profiles/').status_code, 403)

	def test_other_user_cannot_update(self):
		self.client.force_login(self.other)
		response = self.client.patch(self.url, {'bio': 'hacked'}, content_type='application/json')
		self.assertEqual(response.status_code, 403)
		self.owner.profile.refresh_from_db()
		self.assertEqual(self.owner.profile.bio, '')

	def test_owner_can_update_own_profile(self):
		self.client.force_login(self.owner)
		response = self.client.patch(self.url, {'bio': 'Привет'}, content_type='application/json')
		self.assertEqual(response.status_code, 200)
		self.owner.profile.refresh_from_db()
		self.assertEqual(self.owner.profile.bio, 'Привет')

	def test_owner_cannot_reassign_user(self):
		self.client.force_login(self.owner)
		self.client.patch(self.url, {'user': self.other.pk}, content_type='application/json')
		self.owner.profile.refresh_from_db()
		self.assertEqual(self.owner.profile.user_id, self.owner.pk)

	def test_delete_is_not_allowed_even_for_owner(self):
		self.client.force_login(self.owner)
		self.assertEqual(self.client.delete(self.url).status_code, 405)

	def test_profile_fields_are_whitelisted(self):
		self.client.force_login(self.other)
		data = self.client.get(self.url).json()
		self.assertEqual(set(data), {'id', 'user', 'login', 'username', 'avatar', 'bio'})
		self.assertEqual(data['login'], 'owner')

	def test_profiles_list_rejects_post(self):
		self.client.force_login(self.owner)
		self.assertEqual(self.client.post('/api/profiles/', {}, content_type='application/json').status_code, 405)


class CreatePostApiTests(TestCase):
	def setUp(self):
		self.author = User.objects.create_user('author', 'author@example.com', 'pass-12345')
		self.victim = User.objects.create_user('victim', 'victim@example.com', 'pass-12345')
		self.client.force_login(self.author)

	def post_json(self, payload):
		return self.client.post('/api/new-post/', json.dumps(payload), content_type='application/json')

	def test_creates_post_for_current_user(self):
		response = self.post_json({'text': 'Первый пост'})
		self.assertEqual(response.status_code, 200)
		post = Post.objects.get()
		self.assertEqual(post.text, 'Первый пост')
		self.assertEqual(post.author, self.author.profile)

	def test_cannot_spoof_author_or_likes(self):
		self.post_json({
			'text': 'spoof',
			'author': self.victim.pk,
			'likes': [self.victim.profile.pk],
		})
		post = Post.objects.get()
		self.assertEqual(post.author, self.author.profile)
		self.assertEqual(post.likes.count(), 0)

	def test_invalid_data_returns_400_not_500(self):
		response = self.post_json({'text': None})
		self.assertEqual(response.status_code, 400)
		self.assertIn('errors', response.json())
		self.assertFalse(Post.objects.exists())


class LikeAndDeleteApiTests(TestCase):
	def setUp(self):
		self.author = User.objects.create_user('author', 'author@example.com', 'pass-12345')
		self.other = User.objects.create_user('other', 'other@example.com', 'pass-12345')
		self.post = Post.objects.create(author=self.author.profile, text='Пост')

	def call(self, url, payload):
		return self.client.post(url, json.dumps(payload), content_type='application/json')

	def test_like_toggles(self):
		self.client.force_login(self.other)
		first = self.call('/api/like-post/', {'id': str(self.post.pk)}).json()
		self.assertEqual(first, {'likes_count': 1, 'liked': True})
		second = self.call('/api/like-post/', {'id': str(self.post.pk)}).json()
		self.assertEqual(second, {'likes_count': 0, 'liked': False})

	def test_anonymous_cannot_like_or_delete(self):
		for url in ('/api/like-post/', '/api/delete-post/'):
			response = self.call(url, {'id': str(self.post.pk)})
			self.assertNotEqual(response.status_code, 200, url)
		self.assertEqual(self.post.likes.count(), 0)
		self.assertTrue(Post.objects.filter(pk=self.post.pk).exists())

	def test_only_author_can_delete(self):
		self.client.force_login(self.other)
		self.assertEqual(self.call('/api/delete-post/', {'id': str(self.post.pk)}).status_code, 403)
		self.assertTrue(Post.objects.filter(pk=self.post.pk).exists())
		self.client.force_login(self.author)
		self.assertEqual(self.call('/api/delete-post/', {'id': str(self.post.pk)}).status_code, 200)
		self.assertIsNotNone(Post.objects.get(pk=self.post.pk).deleted_at)  # удаление мягкое (149-ФЗ)

	def test_bad_or_missing_id_is_400_or_404_not_500(self):
		self.client.force_login(self.other)
		for url in ('/api/like-post/', '/api/delete-post/'):
			self.assertEqual(self.call(url, {}).status_code, 400, url)
			self.assertEqual(self.call(url, {'id': 'not-a-uuid'}).status_code, 400, url)
			self.assertEqual(self.call(url, {'id': '00000000-0000-0000-0000-000000000000'}).status_code, 404, url)


class FeedPermissionsTests(TestCase):
	def test_following_feed_shows_only_followed_authors(self):
		from customUser.models import FollowThrough
		reader = User.objects.create_user('reader', 'reader@example.com', 'pass-12345')
		followed = User.objects.create_user('followed', 'followed@example.com', 'pass-12345')
		stranger = User.objects.create_user('stranger', 'stranger@example.com', 'pass-12345')
		FollowThrough.objects.create(follower=reader.profile, followee=followed.profile)
		Post.objects.create(author=followed.profile, text='От подписки')
		Post.objects.create(author=stranger.profile, text='От незнакомца')
		self.client.force_login(reader)
		response = self.client.get('/follows-updates/')
		self.assertContains(response, 'От подписки')
		self.assertNotContains(response, 'От незнакомца')
