from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts import relations
from accounts.account import collect_user_data, erase_account
from notifications.models import Notification

from .models import Bookmark, Post
from .pagination import PAGE_SIZE
from .services import delete_post, publish_post, toggle_bookmark, toggle_repost

User = get_user_model()
HX = {'HTTP_HX_REQUEST': 'true'}


class BookmarkTests(TestCase):
	def setUp(self):
		self.ann = User.objects.create_user('ann', 'ann@example.com', 'pass-12345')
		self.bob = User.objects.create_user('bob', 'bob@example.com', 'pass-12345')
		self.post = publish_post(self.ann.profile, 'пост в закладки')
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

	def test_bookmark_of_repost_goes_to_original(self):
		toggle_repost(self.post, self.ann.profile)
		row = Post.objects.get(repost_of=self.post)
		self.client.post(reverse('post-bookmark', args=[row.pk]), **HX)
		self.assertEqual(Bookmark.objects.get().post, self.post)

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

	def test_ordered_and_paged_by_bookmark_time(self):
		posts = [publish_post(self.ann.profile, f'пост {index}') for index in range(PAGE_SIZE + 2)]
		# Закладки в обратном порядке публикации: старый пост, отмеченный последним, — первый в списке.
		for post in reversed(posts):
			toggle_bookmark(post, self.bob.profile)
		response = self.client.get(reverse('bookmarks'))
		self.assertEqual(response.context['posts'][0], posts[0])
		more = self.client.get(response.context['next_url'], **HX)
		self.assertEqual([post.pk for post in more.context['posts']], [posts[-2].pk, posts[-1].pk])

	def test_export_and_erase(self):
		toggle_bookmark(self.post, self.bob.profile)
		data, _ = collect_user_data(self.bob)
		self.assertEqual(data['bookmarks'][0]['post'], self.post.pk)
		erase_account(self.bob)
		self.assertFalse(Bookmark.objects.exists())

	def test_guest_redirected(self):
		self.client.logout()
		self.assertEqual(self.client.get(reverse('bookmarks')).status_code, 302)
		self.assertEqual(self.client.post(reverse('post-bookmark', args=[self.post.pk]), **HX).status_code, 401)
