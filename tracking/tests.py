import json
from datetime import UTC, datetime

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from accounts import relations
from azzb.testing import ACTIVE
from post.services import publish_post

from . import partitions, services
from .models import Impression, InteractionEvent

User = get_user_model()


def make(name, **extra):
	return User.objects.create_user(name, f'{name}@example.com', 'pass-12345', **{**ACTIVE, **extra})


class EventsApiTests(TestCase):
	def setUp(self):
		self.ann = make('ann')
		self.bob = make('bob')
		self.post = publish_post(self.bob.profile, 'привет #котики')
		relations.block(self.bob.profile, self.ann.profile)
		self.client.force_login(self.ann)

	def send(self, items):
		return self.client.post(reverse('api-events'), json.dumps(items), content_type='application/json')

	def test_invisible_post_is_dropped(self):
		self.send([{'kind': 'impression', 'post': str(self.post.pk)}])
		self.assertFalse(Impression.objects.exists())

	def test_guest_and_old_consent_write_nothing(self):
		relations.unblock(self.bob.profile, self.ann.profile)
		self.client.logout()
		self.assertEqual(self.send([{'kind': 'impression', 'post': str(self.post.pk)}]).status_code, 204)
		old = make('old', pd_consent_at=datetime(2026, 11, 1, tzinfo=UTC))
		self.client.force_login(old)
		self.send([{'kind': 'impression', 'post': str(self.post.pk)}])
		self.assertFalse(Impression.objects.exists())


class ConsentTests(TestCase):
	def setUp(self):
		self.legacy = make('legacy', pd_consent_at=None, terms_accepted_at=None)
		self.client.force_login(self.legacy)

	def test_gate_and_accept(self):
		response = self.client.get('/following/')
		self.assertRedirects(response, reverse('consent-update') + '?next=%2Ffollowing%2F', fetch_redirect_response=False)
		self.assertEqual(self.client.get('/rules/').status_code, 200)
		htmx = self.client.post(reverse('post-like', args=['00000000-0000-4000-8000-000000000000']), headers={'HX-Request': 'true'})
		self.assertEqual(htmx['HX-Redirect'], reverse('consent-update'))
		page = self.client.get(reverse('consent-update'))
		self.assertContains(page, 'правила сообщества')
		self.assertEqual(self.client.post(reverse('consent-update'), {'pd_consent': 'on', 'next': '/following/'}).status_code, 200)
		response = self.client.post(reverse('consent-update'), {'pd_consent': 'on', 'accept_rules': 'on', 'next': '/following/'})
		self.assertRedirects(response, '/following/', fetch_redirect_response=False)
		self.legacy.refresh_from_db()
		self.assertIsNotNone(self.legacy.terms_accepted_at)
		self.assertEqual(self.client.get('/following/').status_code, 200)


class RetentionTests(TestCase):
	def tables(self):
		with connection.cursor() as cursor:
			cursor.execute("SELECT relname FROM pg_class WHERE relkind = 'r' AND relname LIKE 'tracking_impression_y%%' ORDER BY relname")
			return [row[0] for row in cursor.fetchall()]

	def test_old_months_dropped_and_ahead_created(self):
		partitions.ensure(datetime(2026, 6, 15, tzinfo=UTC), ahead=0)
		partitions.ensure(datetime(2026, 9, 15, tzinfo=UTC), ahead=0)
		services.purge(datetime(2026, 11, 12, tzinfo=UTC))
		self.assertEqual(self.tables(), ['tracking_impression_y2026m11', 'tracking_impression_y2026m12'])

	def test_events_erased_with_account(self):
		ann, bob = make('ann'), make('bob')
		post = publish_post(bob.profile, 'пост')
		self.client.force_login(ann)
		self.client.get(reverse('post', args=[post.pk]))
		self.assertTrue(InteractionEvent.objects.filter(user=ann).exists())
		self.client.post(reverse('account-delete'), {'confirm': 'pass-12345'})
		self.assertFalse(InteractionEvent.objects.filter(user=ann).exists())
