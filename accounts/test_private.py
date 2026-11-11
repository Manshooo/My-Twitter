from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from django.urls import reverse

from azzb.discover import compute_trends
from notifications.models import Notification
from notifications.services import unread_count
from post.models import Post
from post.services import publish_post

from . import relations
from .models import FollowRequest, FollowThrough
from azzb.testing import ACTIVE

User = get_user_model()
Verb = Notification.Verb
HX = {'HTTP_HX_REQUEST': 'true'}


class PrivateAccountTests(TestCase):
	def setUp(self):
		self.owner, self.fan, self.stranger = (
			User.objects.create_user(name, f'{name}@example.com', 'pass-12345', **ACTIVE) for name in ('owner', 'fan', 'stranger')
		)
		relations.set_private(self.owner.profile, True)
		self.post = publish_post(self.owner.profile, 'только для своих #секрет')

	def visible(self, user):
		return Post.objects.visible_to(user).filter(pk=self.post.pk).exists()

	def follows(self, user):
		return FollowThrough.objects.filter(follower=user.profile, followee=self.owner.profile).exists()

	def test_posts_visible_to_author_and_followers_only(self):
		self.assertTrue(self.visible(self.owner))
		self.assertFalse(self.visible(self.stranger))
		self.assertFalse(self.visible(AnonymousUser()))
		self.assertEqual(relations.follow(self.fan.profile, self.owner.profile), relations.REQUESTED)
		self.assertFalse(self.visible(self.fan))
		relations.approve_request(self.owner.profile, self.fan.profile)
		self.assertTrue(self.visible(self.fan))
		self.assertEqual([row['name'] for row in compute_trends()], [])

	def test_request_flow_and_notifications(self):
		relations.follow(self.fan.profile, self.owner.profile)
		relations.follow(self.fan.profile, self.owner.profile)
		self.assertEqual(FollowRequest.objects.count(), 1)
		self.assertFalse(self.follows(self.fan))
		self.assertTrue(Notification.objects.filter(recipient=self.owner.profile, verb=Verb.FOLLOW_REQUEST).exists())
		self.assertTrue(relations.approve_request(self.owner.profile, self.fan.profile))
		self.assertTrue(self.follows(self.fan))
		self.assertFalse(Notification.objects.filter(verb=Verb.FOLLOW_REQUEST).exists())
		self.assertTrue(Notification.objects.filter(recipient=self.fan.profile, verb=Verb.FOLLOW_ACCEPTED).exists())
		self.assertFalse(relations.approve_request(self.owner.profile, self.fan.profile))

	def test_decline_and_cancel(self):
		relations.follow(self.fan.profile, self.owner.profile)
		relations.decline_request(self.owner.profile, self.fan.profile)
		self.assertFalse(FollowRequest.objects.exists())
		self.assertFalse(Notification.objects.exists())
		relations.follow(self.stranger.profile, self.owner.profile)
		relations.unfollow(self.stranger.profile, self.owner.profile)
		self.assertFalse(FollowRequest.objects.exists())

	def test_opening_account_approves_pending(self):
		relations.follow(self.fan.profile, self.owner.profile)
		relations.set_private(self.owner.profile, False)
		self.assertTrue(self.follows(self.fan))
		self.assertTrue(self.visible(self.stranger))

	def test_block_drops_requests(self):
		relations.follow(self.fan.profile, self.owner.profile)
		relations.block(self.owner.profile, self.fan.profile)
		self.assertFalse(FollowRequest.objects.exists())

	def test_profile_page_for_stranger_and_request_button(self):
		self.client.force_login(self.stranger)
		url = reverse('profile', args=['owner'])
		response = self.client.get(url)
		self.assertContains(response, 'Это закрытый аккаунт')
		self.assertContains(response, 'Отправить заявку')
		self.assertNotContains(response, 'только для своих')
		self.assertIsNone(self.client.get(url, {'tab': 'followers'}).context['people'])
		self.client.post(url, {'subscribe': ''})
		self.assertContains(self.client.get(url), 'Заявка отправлена')

	def test_requests_page_and_answer(self):
		relations.follow(self.fan.profile, self.owner.profile)
		self.client.force_login(self.owner)
		self.assertContains(self.client.get(reverse('profile', args=['owner'])), 'Заявки')
		page = self.client.get(reverse('follow-requests'))
		self.assertContains(page, '@fan')
		self.client.post(reverse('follow-request-answer', args=['fan']), {'approve': ''})
		self.assertTrue(self.follows(self.fan))
		self.assertContains(self.client.get(reverse('follow-requests')), 'Новых заявок нет')

	def test_remove_follower(self):
		relations.follow(self.fan.profile, self.owner.profile)
		relations.approve_request(self.owner.profile, self.fan.profile)
		self.client.force_login(self.owner)
		self.client.post(reverse('profile', args=['fan']), {'remove_follower': ''})
		self.assertFalse(self.follows(self.fan))

	def test_follower_cannot_repost_or_quote(self):
		relations.follow(self.fan.profile, self.owner.profile)
		relations.approve_request(self.owner.profile, self.fan.profile)
		self.client.force_login(self.fan)
		self.assertEqual(self.client.post(reverse('post-repost', args=[self.post.pk]), **HX).status_code, 403)
		response = self.client.post(reverse('compose'), {'text': 'смотрите', 'quote_of': str(self.post.pk)}, **HX)
		self.assertEqual(response.status_code, 403)
		# Ответить можно: ответ — часть обсуждения, которое и так видят подписчики.
		response = self.client.post(reverse('compose'), {'text': 'ответ', 'reply_to': str(self.post.pk)}, **HX)
		self.assertEqual(response.status_code, 200)

	def test_mention_from_private_account_hidden_from_non_follower(self):
		publish_post(self.owner.profile, 'привет @stranger')
		self.assertEqual(unread_count(self.stranger), 0)

	def test_settings_toggle(self):
		relations.follow(self.fan.profile, self.owner.profile)
		self.client.force_login(self.owner)
		self.client.post(reverse('edit-profile'), {'username': 'owner', 'theme': '', 'is_private': 'on'})
		self.owner.profile.refresh_from_db()
		self.assertTrue(self.owner.profile.is_private)
		self.client.post(reverse('edit-profile'), {'username': 'owner', 'theme': ''})
		self.owner.profile.refresh_from_db()
		self.assertFalse(self.owner.profile.is_private)
		self.assertTrue(self.follows(self.fan))
