import json

from django.test import TestCase

from accounts.models import CustomUser
from azzb.testing import ACTIVE
from post.models import Post

# Сама модель, а не get_user_model(): так редактор знает про create_user и поля аккаунта.
User = CustomUser


class ProfileApiPermissionsTests(TestCase):
	@classmethod
	def setUpTestData(cls):
		cls.owner = User.objects.create_user('owner', 'owner@example.com', **ACTIVE)
		cls.other = User.objects.create_user('other', 'other@example.com', **ACTIVE)
		cls.url = f'/api/profiles/{cls.owner.profile.pk}/'

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


class CreatePostApiTests(TestCase):
	def setUp(self):
		self.author = User.objects.create_user('author', 'author@example.com', **ACTIVE)
		self.victim = User.objects.create_user('victim', 'victim@example.com', **ACTIVE)
		self.client.force_login(self.author)

	def post_json(self, payload):
		return self.client.post('/api/new-post/', json.dumps(payload), content_type='application/json')

	def test_cannot_spoof_author_or_likes(self):
		response = self.post_json({
			'text': 'spoof',
			'author': self.victim.pk,
			'likes': [self.victim.profile.pk],
		})
		self.assertEqual(response.status_code, 200)
		post = Post.objects.get()
		self.assertEqual(post.text, 'spoof')
		self.assertEqual(post.author, self.author.profile)
		self.assertEqual(post.likes.count(), 0)


class LikeAndDeleteApiTests(TestCase):
	@classmethod
	def setUpTestData(cls):
		cls.author = User.objects.create_user('author', 'author@example.com', **ACTIVE)
		cls.other = User.objects.create_user('other', 'other@example.com', **ACTIVE)
		cls.post = Post.objects.create(author=cls.author.profile, text='Пост')

	def call(self, url, payload):
		return self.client.post(url, json.dumps(payload), content_type='application/json')

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
		self.assertIsNotNone(Post.objects.get(pk=self.post.pk).deleted_at)  # удаление мягкое (azzb/retention.py)


class FeedPermissionsTests(TestCase):
	def test_following_feed_shows_only_followed_authors(self):
		from accounts.models import FollowThrough
		reader = User.objects.create_user('reader', 'reader@example.com', **ACTIVE)
		followed = User.objects.create_user('followed', 'followed@example.com', **ACTIVE)
		stranger = User.objects.create_user('stranger', 'stranger@example.com', **ACTIVE)
		FollowThrough.objects.create(follower=reader.profile, followee=followed.profile)
		Post.objects.create(author=followed.profile, text='От подписки')
		Post.objects.create(author=stranger.profile, text='От незнакомца')
		self.client.force_login(reader)
		response = self.client.get('/following/')
		self.assertContains(response, 'От подписки')
		self.assertNotContains(response, 'От незнакомца')


class MentionApiTests(TestCase):
	def setUp(self):
		self.me = User.objects.create_user('me', 'me@example.com', **ACTIVE)
		self.anna = User.objects.create_user('anna', 'anna@example.com', **ACTIVE)
		self.annabel = User.objects.create_user('annabel', 'annabel@example.com', **ACTIVE)
		self.client.force_login(self.me)

	def suggest(self, q):
		return [row['username'] for row in self.client.get('/api/users/mention/', {'q': q}).json()['results']]

	def test_suggestions_skip_blocked_and_inactive(self):
		from accounts import relations
		relations.block(self.anna.profile, self.me.profile)
		self.annabel.is_active = False
		self.annabel.save()
		self.assertEqual(self.suggest('ann'), [])
