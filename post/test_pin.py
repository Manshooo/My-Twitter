from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .services import delete_post, publish_post, toggle_repost

User = get_user_model()
HX = {'HTTP_HX_REQUEST': 'true'}


class PinTests(TestCase):
	def setUp(self):
		self.ann = User.objects.create_user('ann', 'ann@example.com', 'pass-12345')
		self.bob = User.objects.create_user('bob', 'bob@example.com', 'pass-12345')
		self.old = publish_post(self.ann.profile, 'старый важный пост')
		self.new = publish_post(self.ann.profile, 'свежий пост')
		self.client.force_login(self.ann)

	def pin(self, post, user=None):
		if user:
			self.client.force_login(user)
		return self.client.post(reverse('post-pin', args=[post.pk]), **HX)

	def profile_posts(self, **params):
		response = self.client.get(reverse('profile', args=['ann']), params)
		return response, list(response.context['posts'])

	def test_pinned_first_once(self):
		response = self.pin(self.old)
		self.assertEqual(response['HX-Refresh'], 'true')
		self.client.force_login(self.bob)
		response, posts = self.profile_posts()
		self.assertEqual(response.context['pinned'], self.old)
		self.assertEqual(posts, [self.new])
		self.assertContains(response, 'Закреплённый пост')

	def test_toggle_and_replace(self):
		self.pin(self.old)
		self.pin(self.new)
		self.ann.profile.refresh_from_db()
		self.assertEqual(self.ann.profile.pinned_post, self.new)
		self.pin(self.new)
		self.ann.profile.refresh_from_db()
		self.assertIsNone(self.ann.profile.pinned_post)

	def test_only_own_non_repost(self):
		self.assertEqual(self.pin(self.old, user=self.bob).status_code, 403)
		toggle_repost(self.old, self.bob.profile)
		row = self.old.reposts.get()
		self.assertEqual(self.pin(row, user=self.bob).status_code, 403)

	def test_deleted_pinned_disappears(self):
		self.pin(self.old)
		delete_post(self.old)
		response, posts = self.profile_posts()
		self.assertIsNone(response.context['pinned'])
		self.assertEqual(posts, [self.new])

	def test_menu_label(self):
		self.pin(self.old)
		response = self.client.get(reverse('post', args=[self.old.pk]))
		self.assertContains(response, 'Открепить в профиле')
