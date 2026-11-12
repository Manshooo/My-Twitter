from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts import relations
from post.models import HOT_WINDOW, Post
from post.services import publish_post, toggle_like, toggle_repost
from azzb.testing import ACTIVE

User = get_user_model()


class HotFeedTests(TestCase):
	def setUp(self):
		self.users = [User.objects.create_user(f'u{i}', f'u{i}@example.com', 'pass-12345', **ACTIVE) for i in range(6)]
		self.author = self.users[0]

	def age(self, post, hours):
		Post.objects.filter(pk=post.pk).update(created_at=timezone.now() - timedelta(hours=hours))

	def hot(self):
		# Гостю главная — «Популярное» без личных множителей, то есть «Горячее».
		return list(self.client.get(reverse('index')).context['posts'])

	def test_fresh_discussion_beats_old_popularity(self):
		old = publish_post(self.author.profile, 'старый популярный')
		for user in self.users[1:]:
			toggle_like(old, user.profile)
		self.age(old, 48)  # 5 / 50^1.5 ≈ 0.014
		fresh = publish_post(self.author.profile, 'свежий')
		toggle_like(fresh, self.users[1].profile)  # 1 / 2^1.5 ≈ 0.35
		self.assertEqual(self.hot(), [fresh, old])

	def test_replies_and_reposts_weigh_more_than_likes(self):
		liked = publish_post(self.author.profile, 'лайки')
		discussed = publish_post(self.author.profile, 'обсуждение')
		for user in self.users[1:3]:
			toggle_like(liked, user.profile)  # 2
		publish_post(self.users[1].profile, 'ответ', reply_to=discussed)  # 2
		toggle_repost(discussed, self.users[2].profile)  # 3
		self.assertEqual(self.hot()[:2], [discussed, liked])

	def test_window_reposts_and_mute(self):
		ancient = publish_post(self.author.profile, 'давно')
		self.age(ancient, HOT_WINDOW.total_seconds() / 3600 + 1)
		post = publish_post(self.users[1].profile, 'пост')
		toggle_repost(post, self.author.profile)
		self.assertEqual(self.hot(), [post])
		self.client.force_login(self.author)
		relations.mute(self.author.profile, self.users[1].profile)
		self.assertContains(self.client.get(reverse('index')), 'За неделю пока тихо')


class QuotesRankingTests(TestCase):
	"""Цитаты в оценке (docs/feed.md): считаются отдельно от репостов, а «ratio» — много цитат и
	ответов при малом одобрении — опускает пост, но не ниже половины оценки."""

	def setUp(self):
		self.users = [User.objects.create_user(f'q{i}', f'q{i}@example.com', 'pass-12345', **ACTIVE) for i in range(6)]
		self.author = self.users[0]

	def ranked(self):
		return [post.text for post in Post.objects.for_feed(None).top_level().hot()]

	def test_dunked_post_ranks_below_liked(self):
		calm = publish_post(self.author.profile, 'спокойный')
		dunked = publish_post(self.author.profile, 'спорный')
		for user in self.users[1:5]:
			toggle_like(calm, user.profile)  # 4, спорность 1
		for user in self.users[1:4]:
			publish_post(user.profile, 'ну и ну', quote_of=dunked)  # 2·3 = 6, спорность 2·1/4 = 0,5 → 3
		self.assertEqual(self.ranked()[:2], ['спокойный', 'спорный'])
		self.assertEqual(Post.objects.for_feed(None).top_level().hot().get(pk=dunked.pk).quotes_n, 3)

	def test_quote_by_follow_lifts_post(self):
		from accounts.models import FollowThrough
		me, friend, stranger = self.users[1], self.users[2], self.users[3]
		FollowThrough.objects.create(follower=me.profile, followee=friend.profile)
		first = publish_post(self.author.profile, 'процитировал незнакомец')
		second = publish_post(self.author.profile, 'процитировал друг')
		publish_post(stranger.profile, 'цитата', quote_of=first)
		publish_post(friend.profile, 'цитата', quote_of=second)
		feed = [post.text for post in Post.objects.for_feed(me).top_level().for_you(me) if post.author_id == self.author.pk]
		self.assertEqual(feed, ['процитировал друг', 'процитировал незнакомец'])
