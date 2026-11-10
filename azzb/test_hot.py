from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts import relations
from post.models import HOT_WINDOW, Post
from post.services import publish_post, toggle_like, toggle_repost

User = get_user_model()


class HotFeedTests(TestCase):
	def setUp(self):
		self.users = [User.objects.create_user(f'u{i}', f'u{i}@example.com', 'pass-12345') for i in range(6)]
		self.author = self.users[0]

	def age(self, post, hours):
		Post.objects.filter(pk=post.pk).update(created_at=timezone.now() - timedelta(hours=hours))

	def hot(self):
		return list(self.client.get(reverse('hot-news')).context['posts'])

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
		self.assertContains(self.client.get(reverse('hot-news')), 'Пока ничего горячего')
