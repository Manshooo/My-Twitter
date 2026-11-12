from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts import relations
from post.models import Post
from post.services import delete_post, publish_post

from .discover import compute_trends, who_to_follow
from azzb.testing import ACTIVE

User = get_user_model()


def make(name):
	return User.objects.create_user(name, f'{name}@example.com', 'pass-12345', **ACTIVE)


class WhoToFollowTests(TestCase):
	def setUp(self):
		self.me, self.friend, self.fof, self.star, self.muted = (make(n) for n in ('me', 'friend', 'fof', 'star', 'muted'))
		relations.follow(self.me.profile, self.friend.profile)
		relations.follow(self.friend.profile, self.fof.profile)
		for user in (self.friend, self.fof, self.muted):
			relations.follow(user.profile, self.star.profile)
		relations.mute(self.me.profile, self.muted.profile)

	def test_friends_of_friends_first_then_popular(self):
		# pop популярнее fof (3 подписчика против 1), но его не читает никто из моих подписок.
		pop = make('pop')
		for user in (self.star, self.muted, self.fof):
			relations.follow(user.profile, pop.profile)
		people = who_to_follow(self.me, 10)
		self.assertEqual(people, [self.star.profile, self.fof.profile, pop.profile])
		self.assertEqual([person.mutual for person in people], [1, 1, 0])

	def test_excludes_blocked_banned_and_followed(self):
		relations.block(self.star.profile, self.me.profile)
		self.fof.banned_until = timezone.now() + timedelta(days=1)
		self.fof.save()
		self.assertEqual(who_to_follow(self.me, 10), [])

	def test_guest_gets_popular_and_page(self):
		from django.contrib.auth.models import AnonymousUser
		self.assertEqual(who_to_follow(AnonymousUser(), 1), [self.star.profile])
		self.client.force_login(self.me)
		response = self.client.get(reverse('who-to-follow'))
		self.assertContains(response, 'Читают 1 из ваших подписок')


class TrendsTests(TestCase):
	def setUp(self):
		self.ann, self.bob, self.cat = (make(n) for n in ('ann', 'bob', 'cat'))
		cache.clear()

	def test_ranked_by_distinct_authors_within_a_day(self):
		for _ in range(5):
			publish_post(self.ann.profile, 'спам #реклама')
		publish_post(self.ann.profile, '#новости')
		publish_post(self.bob.profile, '#новости')
		old = publish_post(self.cat.profile, '#вчера')
		Post.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(hours=25))
		self.assertEqual(
			[(row['name'], row['authors'], row['uses']) for row in compute_trends()],
			[('новости', 2, 2), ('реклама', 1, 5)],
		)

	def test_skips_deleted_and_banned(self):
		delete_post(publish_post(self.ann.profile, '#удалён'))
		publish_post(self.bob.profile, '#бан')
		self.bob.banned_until = timezone.now() + timedelta(days=1)
		self.bob.save()
		self.assertEqual(compute_trends(), [])

	def test_shown_in_rail_and_on_search_page(self):
		publish_post(self.ann.profile, '#погода')
		self.client.force_login(self.bob)
		self.assertContains(self.client.get(reverse('index')), 'Тренды за сутки')
		self.assertContains(self.client.get(reverse('search')), '#погода', count=2)
