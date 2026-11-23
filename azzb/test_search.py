from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts import relations
from azzb.testing import ACTIVE
from post.services import delete_post, edit_post, publish_post, toggle_repost

User = get_user_model()


class SearchTests(TestCase):
	def setUp(self):
		self.ann = User.objects.create_user('ann', 'ann@example.com', **ACTIVE)
		self.bob = User.objects.create_user('bob_builder', 'bob@example.com', **ACTIVE)
		self.client.force_login(self.ann)

	def search(self, q, **params):
		return self.client.get(reverse('search'), {'q': q, **params})

	def test_posts_follow_visibility_and_skip_reposts(self):
		post = publish_post(self.bob.profile, 'секретный рецепт')
		toggle_repost(post, self.ann.profile)
		self.assertEqual(self.search('рецепт').context['posts'], [post])
		relations.mute(self.ann.profile, self.bob.profile)
		self.assertEqual(self.search('рецепт').context['posts'], [])
		relations.unmute(self.ann.profile, self.bob.profile)
		edit_post(post, 'другой текст')
		self.assertEqual(self.search('рецепт').context['posts'], [])
		delete_post(post)
		self.assertEqual(self.search('текст').context['posts'], [])
