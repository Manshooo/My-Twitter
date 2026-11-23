from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts import relations
from azzb.testing import ACTIVE
from notifications.models import Notification

from .models import Bookmark
from .services import delete_post, publish_post, toggle_bookmark

User = get_user_model()
HX = {'HTTP_HX_REQUEST': 'true'}


class BookmarkTests(TestCase):
	@classmethod
	def setUpTestData(cls):
		cls.ann = User.objects.create_user('ann', 'ann@example.com', **ACTIVE)
		cls.bob = User.objects.create_user('bob', 'bob@example.com', **ACTIVE)
		cls.post = publish_post(cls.ann.profile, 'пост в закладки')

	def setUp(self):
		self.client.force_login(self.bob)

	def test_toggle_is_private(self):
		response = self.client.post(reverse('post-bookmark', args=[self.post.pk]), **HX)
		self.assertContains(response, 'aria-pressed="true"')
		self.assertTrue(Bookmark.objects.filter(profile=self.bob.profile, post=self.post).exists())
		# Автор не узнаёт о закладке.
		self.assertFalse(Notification.objects.exists())
		response = self.client.post(reverse('post-bookmark', args=[self.post.pk]), **HX)
		self.assertContains(response, 'aria-pressed="false"')
		self.assertFalse(Bookmark.objects.exists())

	def test_page_lists_only_mine_and_visible(self):
		other = publish_post(self.ann.profile, 'чужая закладка')
		toggle_bookmark(other, self.ann.profile)
		toggle_bookmark(self.post, self.bob.profile)
		response = self.client.get(reverse('bookmarks'))
		self.assertContains(response, 'пост в закладки')
		self.assertNotContains(response, 'чужая закладка')
		self.assertContains(response, 'bookmarked')
		relations.block(self.bob.profile, self.ann.profile)
		self.assertNotContains(self.client.get(reverse('bookmarks')), 'пост в закладки')
		relations.unblock(self.bob.profile, self.ann.profile)
		delete_post(self.post)
		self.assertContains(self.client.get(reverse('bookmarks')), 'Закладок пока нет')
