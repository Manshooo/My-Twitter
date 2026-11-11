from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts import relations
from accounts.account import erase_account
from post.services import delete_post, publish_post, toggle_like

from .models import Notification
from .services import grouped_page, unread_count

User = get_user_model()
Verb = Notification.Verb


class NotificationTests(TestCase):
	def setUp(self):
		self.ann, self.bob, self.cat = (User.objects.create_user(name, f'{name}@example.com', 'pass-12345') for name in ('ann', 'bob', 'cat'))
		self.post = publish_post(self.ann.profile, 'привет')

	def test_like_notifies_author_and_unlike_retracts(self):
		toggle_like(self.post, self.bob.profile)
		self.assertEqual(unread_count(self.ann), 1)
		toggle_like(self.post, self.bob.profile)
		self.assertEqual(unread_count(self.ann), 0)

	def test_own_actions_do_not_notify(self):
		toggle_like(self.post, self.ann.profile)
		publish_post(self.ann.profile, 'сам себе', reply_to=self.post)
		self.assertFalse(Notification.objects.exists())

	def test_reply_and_follow_notify(self):
		reply = publish_post(self.bob.profile, 'ответ', reply_to=self.post)
		relations.follow(self.cat.profile, self.ann.profile)
		self.assertEqual(
			set(Notification.objects.filter(recipient=self.ann.profile).values_list('verb', 'post')),
			{(Verb.REPLY, reply.pk), (Verb.FOLLOW, None)},
		)
		relations.unfollow(self.cat.profile, self.ann.profile)
		self.assertEqual(unread_count(self.ann), 1)

	def test_repeated_follow_is_one_notification(self):
		relations.follow(self.bob.profile, self.ann.profile)
		relations.follow(self.bob.profile, self.ann.profile)
		self.assertEqual(Notification.objects.count(), 1)

	def test_likes_on_one_post_are_grouped(self):
		toggle_like(self.post, self.bob.profile)
		toggle_like(self.post, self.cat.profile)
		relations.follow(self.bob.profile, self.ann.profile)
		groups, _ = grouped_page(self.ann)
		likes = next(group for group in groups if group['verb'] == Verb.LIKE)
		self.assertEqual(len(groups), 2)
		self.assertEqual(likes['total'], 2)
		# Свежие — первыми.
		self.assertEqual(likes['actors'][0], self.cat.profile)

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

	def test_page_marks_read_and_shows_groups(self):
		toggle_like(self.post, self.bob.profile)
		publish_post(self.cat.profile, 'ответ кота', reply_to=self.post)
		self.client.force_login(self.ann)
		response = self.client.get(reverse('notifications'))
		self.assertContains(response, 'лайкнул(а) ваш пост')
		self.assertContains(response, 'ответ кота')
		self.assertContains(response, 'notif-unread')
		self.assertEqual(unread_count(self.ann), 0)
		self.assertNotContains(self.client.get(reverse('notifications')), 'notif-unread')

	def test_pagination(self):
		for index in range(25):
			publish_post(self.bob.profile, f'ответ {index}', reply_to=self.post)
		groups, before = grouped_page(self.ann)
		self.assertEqual(len(groups), 20)
		self.client.force_login(self.ann)
		response = self.client.get(reverse('notifications'), {'before': before.isoformat()}, HTTP_HX_REQUEST='true')
		self.assertContains(response, 'ответ 4')
		self.assertNotContains(response, 'ответ 5<')

	def test_badge_endpoint(self):
		toggle_like(self.post, self.bob.profile)
		self.client.force_login(self.ann)
		response = self.client.get(reverse('notifications-unread'), HTTP_HX_REQUEST='true')
		self.assertContains(response, 'id="notif-badge-tab"')
		self.assertContains(response, 'hx-swap-oob="true"')
		self.assertContains(response, '>1<')
		self.client.logout()
		self.assertEqual(self.client.get(reverse('notifications-unread'), HTTP_HX_REQUEST='true').status_code, 401)

	def test_erase_account_removes_notifications(self):
		toggle_like(self.post, self.bob.profile)
		relations.follow(self.ann.profile, self.bob.profile)
		erase_account(self.bob)
		self.assertFalse(Notification.objects.exists())


class RealtimeSignalTests(TestCase):
	"""F3: значки обновляются по сигналу из сокета, а не только опросом."""

	def setUp(self):
		self.ann, self.bob = (User.objects.create_user(name, f'{name}@example.com', 'pass-12345') for name in ('ann', 'bob'))
		self.post = publish_post(self.ann.profile, 'привет')

	def test_new_notification_signals_recipient_once(self):
		with mock.patch('notifications.services.push') as push:
			toggle_like(self.post, self.bob.profile)
			toggle_like(self.post, self.ann.profile)  # свой лайк — без уведомления
		push.assert_called_once_with([self.ann.pk], 'notifications')

	def test_retract_and_read_refresh_badges(self):
		toggle_like(self.post, self.bob.profile)
		with mock.patch('notifications.services.push') as push:
			toggle_like(self.post, self.bob.profile)
		push.assert_called_once_with([self.ann.pk], 'badges')
		toggle_like(self.post, self.bob.profile)
		with mock.patch('notifications.services.push') as push:
			self.client.force_login(self.ann)
			self.client.get(reverse('notifications'))
			self.client.get(reverse('notifications'))  # читать уже нечего — сигнала нет
		push.assert_called_once_with([self.ann.pk], 'badges')
