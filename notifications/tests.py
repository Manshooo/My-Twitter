from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from accounts import relations
from azzb.testing import ACTIVE
from post.services import delete_post, publish_post, toggle_like

from .models import Notification
from .services import unread_count

User = get_user_model()
Verb = Notification.Verb


class NotificationTests(TestCase):
	@classmethod
	def setUpTestData(cls):
		cls.ann, cls.bob, cls.cat = (User.objects.create_user(name, f'{name}@example.com', **ACTIVE) for name in ('ann', 'bob', 'cat'))
		cls.post = publish_post(cls.ann.profile, 'привет')

	def test_like_notifies_author_and_unlike_retracts(self):
		toggle_like(self.post, self.bob.profile)
		self.assertEqual(unread_count(self.ann), 1)
		toggle_like(self.post, self.bob.profile)
		self.assertEqual(unread_count(self.ann), 0)

	def test_hidden_when_blocked_muted_banned_or_post_deleted(self):
		toggle_like(self.post, self.bob.profile)
		relations.follow(self.cat.profile, self.ann.profile)
		self.assertEqual(unread_count(self.ann), 2)
		relations.mute(self.ann.profile, self.cat.profile)
		self.assertEqual(unread_count(self.ann), 1)
		self.bob.banned_until = timezone.now() + timedelta(days=1)
		self.bob.save()
		self.assertEqual(unread_count(self.ann), 0)
		self.bob.banned_until = None
		self.bob.save()
		relations.block(self.ann.profile, self.bob.profile)
		self.assertEqual(unread_count(self.ann), 0)
		relations.unblock(self.ann.profile, self.bob.profile)
		self.assertEqual(unread_count(self.ann), 1)
		delete_post(self.post)
		self.assertEqual(unread_count(self.ann), 0)
