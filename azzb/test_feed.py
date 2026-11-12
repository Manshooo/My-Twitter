from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import FeedSort, FollowThrough
from post.models import FOR_YOU_WINDOW, Post
from post.services import publish_post, toggle_like, toggle_repost
from azzb.testing import ACTIVE

User = get_user_model()


class ForYouTests(TestCase):
	"""«Для вас» (docs/feed.md): оценка «Горячего» × личные множители."""

	def setUp(self):
		self.me, self.friend, self.stranger, self.other = (
			User.objects.create_user(name, f'{name}@example.com', 'pass-12345', **ACTIVE)
			for name in ('me', 'friend', 'stranger', 'other')
		)
		self.client.force_login(self.me)

	def feed(self):
		return [post.text for post in self.client.get(reverse('index')).context['posts']]

	def follow(self, who):
		FollowThrough.objects.create(follower=self.me.profile, followee=who.profile)

	def test_followed_author_beats_equal_stranger(self):
		publish_post(self.stranger.profile, 'чужой')
		publish_post(self.friend.profile, 'друг')
		self.follow(self.friend)
		self.assertEqual(self.feed()[0], 'друг')

	def test_liked_by_follows_beats_equal_post(self):
		self.follow(self.friend)
		plain = publish_post(self.stranger.profile, 'просто')
		social = publish_post(self.other.profile, 'лайкнул друг')
		toggle_like(social, self.friend.profile)
		toggle_like(plain, self.stranger.profile)  # та же вовлечённость
		self.assertEqual(self.feed()[0], 'лайкнул друг')

	def test_liked_hashtag_and_author_lift_posts(self):
		liked = publish_post(self.other.profile, 'про #котики')
		toggle_like(liked, self.me.profile)
		publish_post(self.stranger.profile, 'про собак')
		publish_post(self.stranger.profile, 'снова #котики')
		feed = self.feed()
		self.assertLess(feed.index('снова #котики'), feed.index('про собак'))

	def test_window_and_no_reposts(self):
		old = publish_post(self.friend.profile, 'давно')
		Post.objects.filter(pk=old.pk).update(created_at=timezone.now() - FOR_YOU_WINDOW - timedelta(hours=1))
		post = publish_post(self.stranger.profile, 'пост')
		toggle_repost(post, self.friend.profile)
		self.assertEqual(self.feed(), ['пост'])

	def test_new_sort_is_chronological_and_remembered(self):
		publish_post(self.stranger.profile, 'первый')
		second = publish_post(self.stranger.profile, 'второй')
		toggle_like(second, self.friend.profile)
		older_popular = Post.objects.get(text='первый')
		for user in (self.friend, self.other):
			toggle_like(older_popular, user.profile)
		self.assertEqual(self.feed(), ['первый', 'второй'])
		response = self.client.post(reverse('feed-sort'), {'sort': 'new'})
		self.assertRedirects(response, reverse('index'))
		self.me.profile.refresh_from_db()
		self.assertEqual(self.me.profile.feed_sort, FeedSort.NEW)
		self.assertEqual(self.feed(), ['второй', 'первый'])
		self.client.post(reverse('feed-sort'), {'sort': 'nonsense'})
		self.me.profile.refresh_from_db()
		self.assertEqual(self.me.profile.feed_sort, FeedSort.NEW)

	def test_tabs_and_sort_chip(self):
		html = self.client.get(reverse('index')).content.decode()
		self.assertIn('class="tab" href="/" aria-current="page"', html)
		self.assertIn('href="/following/"', html)
		self.assertIn('aria-controls="feed-sort-menu"', html)
		html = self.client.get(reverse('following')).content.decode()
		self.assertIn('class="tab" href="/following/" aria-current="page"', html)
		self.assertNotIn('feed-sort-menu', html)

	def test_guest_has_no_tabs(self):
		self.client.logout()
		self.assertNotContains(self.client.get(reverse('index')), 'class="tabs')


class FeedSeoTests(TestCase):
	def test_sitemap_has_no_hot_page(self):
		body = self.client.get(reverse('sitemap-section', kwargs={'section': 'pages'})).content.decode()
		self.assertNotIn('/hot/', body)
		self.assertIn('<loc>http://testserver/</loc>', body)

	def test_robots_closes_following(self):
		self.assertContains(self.client.get('/robots.txt'), 'Disallow: /following/')
