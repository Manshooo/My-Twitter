import json
from datetime import datetime, timezone

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from accounts import relations
from azzb.testing import ACTIVE
from post.services import publish_post

from . import partitions, services
from .models import Impression, InteractionEvent, NegativeFeedback

User = get_user_model()


def make(name, **extra):
	return User.objects.create_user(name, f'{name}@example.com', 'pass-12345', **{**ACTIVE, **extra})


class EventsApiTests(TestCase):
	def setUp(self):
		self.ann = make('ann')
		self.bob = make('bob')
		self.post = publish_post(self.bob.profile, 'привет #котики')
		self.hidden = publish_post(self.bob.profile, 'закрыто')
		relations.block(self.bob.profile, self.ann.profile)
		self.client.force_login(self.ann)

	def send(self, items):
		return self.client.post(reverse('api-events'), json.dumps(items), content_type='application/json')

	def test_writes_only_visible_known_and_once_per_feed(self):
		relations.unblock(self.bob.profile, self.ann.profile)
		feed = '2b8f3c4e-0000-4000-8000-000000000001'
		response = self.send([
			{'kind': 'impression', 'post': str(self.post.pk), 'feed': feed, 'surface': 'latest', 'position': 0},
			{'kind': 'impression', 'post': str(self.post.pk), 'feed': feed, 'surface': 'latest', 'position': 0},
			{'kind': 'dwell', 'post': str(self.post.pk), 'feed': feed, 'seconds': 7},
			{'kind': 'dwell', 'post': str(self.post.pk), 'seconds': 100000},
			{'kind': 'tag_click', 'post': str(self.post.pk), 'tag': 'котики'},
			{'kind': 'tag_click', 'post': str(self.post.pk), 'tag': 'выдуманный'},
			{'kind': 'link_click', 'post': str(self.post.pk), 'domain': 'example.com/path'},
			{'kind': 'open', 'post': str(self.post.pk)},
			{'kind': 'search_click', 'result': 'person'},
			'мусор',
		])
		self.assertEqual(response.status_code, 204)
		self.assertEqual(list(Impression.objects.values_list('kind', 'surface', 'seconds')), [
			('impression', 'latest', None), ('dwell', 'other', 7),
		])
		self.assertEqual(
			sorted(InteractionEvent.objects.values_list('kind', flat=True)), ['search_click', 'tag_click'],
		)

	def test_invisible_post_is_dropped(self):
		self.send([{'kind': 'impression', 'post': str(self.post.pk)}])
		self.assertFalse(Impression.objects.exists())

	def test_guest_and_old_consent_write_nothing(self):
		relations.unblock(self.bob.profile, self.ann.profile)
		self.client.logout()
		self.assertEqual(self.send([{'kind': 'impression', 'post': str(self.post.pk)}]).status_code, 204)
		old = make('old', pd_consent_at=datetime(2026, 11, 1, tzinfo=timezone.utc))
		self.client.force_login(old)
		self.send([{'kind': 'impression', 'post': str(self.post.pk)}])
		self.assertFalse(Impression.objects.exists())

	def test_tracker_url_only_for_collecting_users(self):
		self.assertContains(self.client.get('/'), 'data-surface="latest"')
		self.client.logout()
		self.assertNotContains(self.client.get('/'), 'data-events-url')


class ServerEventsTests(TestCase):
	def setUp(self):
		self.ann = make('ann')
		self.bob = make('bob')
		self.post = publish_post(self.bob.profile, 'пост')
		self.client.force_login(self.ann)

	def kinds(self):
		return list(InteractionEvent.objects.order_by('id').values_list('kind', 'surface'))

	def test_open_unlike_unfollow_search(self):
		self.client.get(reverse('post', args=[self.post.pk]), headers={'Referer': 'http://testserver/hot/'})
		like = reverse('post-like', args=[self.post.pk])
		self.client.post(like)
		self.client.post(like)
		relations.follow(self.ann.profile, self.bob.profile)
		self.client.post(reverse('profile', args=['bob']), {'unsubscribe': '1'})
		self.client.get(reverse('search'), {'q': 'котики'})
		self.client.get(reverse('search'), {'q': 'котики', 'page': 2})
		self.assertEqual(self.kinds(), [
			('open', 'hot'), ('unlike', 'other'), ('unfollow', 'other'), ('search', 'search'),
		])
		self.assertEqual(InteractionEvent.objects.get(kind='search').data, {'query': 'котики', 'tab': 'posts'})


class NotInterestedTests(TestCase):
	def setUp(self):
		self.ann = make('ann')
		self.bob = make('bob')
		self.cat = make('cat')
		self.first = publish_post(self.bob.profile, 'первый #погода')
		self.second = publish_post(self.bob.profile, 'второй')
		self.other = publish_post(self.cat.profile, 'про #погода')
		self.client.force_login(self.ann)

	def mark(self, post, what, **extra):
		return self.client.post(
			reverse('post-not-interested', args=[post.pk]), {'what': what, **extra}, headers={'HX-Request': 'true'},
		)

	def feed(self, url='/'):
		return [str(post.pk) for post in self.client.get(url).context['posts']]

	def test_post_author_and_tag(self):
		response = self.mark(self.second, 'post')
		self.assertEqual(response.status_code, 204)
		self.assertIn('azzb:hide-post', response['HX-Trigger'])
		self.assertNotIn(str(self.second.pk), self.feed())
		self.mark(self.other, 'tag', tag='погода')
		self.assertEqual(self.feed(), [])
		self.assertEqual(self.feed(reverse('hashtag', args=['погода'])), [str(self.other.pk), str(self.first.pk)])
		self.assertEqual(InteractionEvent.objects.filter(kind='not_interested').count(), 2)

	def test_author_hidden_from_latest_and_hot_but_not_following(self):
		self.mark(self.first, 'author')
		self.assertEqual(self.feed(), [str(self.other.pk)])
		self.assertNotIn(str(self.first.pk), self.feed(reverse('hot-news')))
		relations.follow(self.ann.profile, self.bob.profile)
		self.assertEqual(len(self.feed(reverse('follows-updates'))), 2)

	def test_own_post_and_unknown_tag_rejected(self):
		self.client.force_login(self.bob)
		self.assertEqual(self.mark(self.first, 'post').status_code, 400)
		self.client.force_login(self.ann)
		self.assertEqual(self.mark(self.first, 'tag', tag='нет-такого').status_code, 400)

	def test_settings_list_and_forget(self):
		self.mark(self.first, 'author')
		page = self.client.get(reverse('blocked-accounts'))
		self.assertContains(page, '@bob')
		mark = NegativeFeedback.objects.get()
		self.client.post(reverse('not-interested-forget', args=[mark.pk]))
		self.assertFalse(NegativeFeedback.objects.exists())


class ConsentTests(TestCase):
	def setUp(self):
		self.legacy = make('legacy', pd_consent_at=None, terms_accepted_at=None)
		self.client.force_login(self.legacy)

	def test_gate_and_accept(self):
		response = self.client.get('/hot/')
		self.assertRedirects(response, reverse('consent-update') + '?next=%2Fhot%2F', fetch_redirect_response=False)
		self.assertEqual(self.client.get('/rules/').status_code, 200)
		htmx = self.client.post(reverse('post-like', args=['00000000-0000-4000-8000-000000000000']), headers={'HX-Request': 'true'})
		self.assertEqual(htmx['HX-Redirect'], reverse('consent-update'))
		page = self.client.get(reverse('consent-update'))
		self.assertContains(page, 'правила сообщества')
		self.assertEqual(self.client.post(reverse('consent-update'), {'pd_consent': 'on', 'next': '/hot/'}).status_code, 200)
		response = self.client.post(reverse('consent-update'), {'pd_consent': 'on', 'accept_rules': 'on', 'next': '/hot/'})
		self.assertRedirects(response, '/hot/', fetch_redirect_response=False)
		self.legacy.refresh_from_db()
		self.assertIsNotNone(self.legacy.terms_accepted_at)
		self.assertEqual(self.client.get('/hot/').status_code, 200)


class RetentionTests(TestCase):
	def tables(self):
		with connection.cursor() as cursor:
			cursor.execute("SELECT relname FROM pg_class WHERE relkind = 'r' AND relname LIKE 'tracking_impression_y%%' ORDER BY relname")
			return [row[0] for row in cursor.fetchall()]

	def test_old_months_dropped_and_ahead_created(self):
		partitions.ensure(datetime(2026, 6, 15, tzinfo=timezone.utc), ahead=0)
		partitions.ensure(datetime(2026, 9, 15, tzinfo=timezone.utc), ahead=0)
		services.purge(datetime(2026, 11, 12, tzinfo=timezone.utc))
		self.assertEqual(self.tables(), ['tracking_impression_y2026m11', 'tracking_impression_y2026m12'])

	def test_events_erased_with_account(self):
		ann, bob = make('ann'), make('bob')
		post = publish_post(bob.profile, 'пост')
		self.client.force_login(ann)
		self.client.get(reverse('post', args=[post.pk]))
		self.assertTrue(InteractionEvent.objects.filter(user=ann).exists())
		self.client.post(reverse('account-delete'), {'confirm': 'pass-12345'})
		self.assertFalse(InteractionEvent.objects.filter(user=ann).exists())
