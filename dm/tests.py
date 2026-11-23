from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts import relations
from accounts.account import erase_account
from accounts.models import DmPolicy
from azzb.consumers import UserConsumer
from azzb.testing import ACTIVE, ConsumerTestCase, WebsocketClient

from . import services
from .models import Member, Message

User = get_user_model()
HTMX = {'HTTP_HX_REQUEST': 'true'}


def users(*names):
	return [User.objects.create_user(name, f'{name}@example.com', 'pass-12345', **ACTIVE) for name in names]


class RulesTests(TestCase):
	def setUp(self):
		self.ann, self.bob = users('ann', 'bob')
		self.a, self.b = self.ann.profile, self.bob.profile

	def set_policy(self, profile, policy):
		profile.dm_policy = policy
		profile.save(update_fields=['dm_policy'])

	def test_following_policy(self):
		self.set_policy(self.b, DmPolicy.FOLLOWING)
		self.assertIn('только от тех', services.refusal(self.a, self.b))
		relations.follow(self.a, self.b)  # ann читает bob — не то направление
		self.assertIsNotNone(services.refusal(self.a, self.b))
		relations.follow(self.b, self.a)
		self.assertIsNone(services.refusal(self.a, self.b))

	def test_nobody_still_allows_reply_to_own_conversation(self):
		self.set_policy(self.a, DmPolicy.NOBODY)
		member, _ = services.send_message(self.a, self.b, 'привет')
		peer_member = services.find_member(self.b, self.a)
		self.assertIsNone(services.refusal(self.b, self.a, peer_member.conversation))
		self.set_policy(self.b, DmPolicy.NOBODY)
		self.assertIn('не принимает', services.refusal(self.a, self.b, member.conversation))

	def test_blocks_both_ways(self):
		relations.block(self.b, self.a)
		self.assertIsNotNone(services.refusal(self.a, self.b))
		self.assertIn('Разблокируйте', services.refusal(self.b, self.a))


class ConversationTests(TestCase):
	def setUp(self):
		ann, bob = users('ann', 'bob')
		self.a, self.b = ann.profile, bob.profile

	def test_delete_only_own(self):
		member, message = services.send_message(self.a, self.b, 'секрет')
		self.assertFalse(services.delete_message(services.find_member(self.b, self.a), message.pk))
		self.assertTrue(services.delete_message(member, message.pk))
		message.refresh_from_db()
		self.assertIsNotNone(message.deleted_at)
		self.assertEqual(message.text, 'секрет')  # стирается по сроку хранения


class RetentionTests(TestCase):
	def setUp(self):
		self.ann, self.bob = users('ann', 'bob')

	def test_erase_account_purges_sent_messages(self):
		services.send_message(self.ann.profile, self.bob.profile, 'от ann')
		services.send_message(self.bob.profile, self.ann.profile, 'от bob', member=services.find_member(self.bob.profile, self.ann.profile))
		erase_account(self.ann)
		self.assertEqual(Message.objects.get(sender=self.ann.profile).text, '')
		self.assertEqual(Message.objects.get(sender=self.bob.profile).text, 'от bob')
		self.assertFalse(Member.objects.filter(profile=self.ann.profile).exists())
		self.assertEqual(len(services.inbox(self.bob.profile)[0]), 1)


class ViewTests(TestCase):
	def setUp(self):
		self.ann, self.bob, self.cat = users('ann', 'bob', 'cat')
		self.client.force_login(self.ann)

	def test_start_send_and_read(self):
		url = reverse('dm-start', args=['bob'])
		self.assertContains(self.client.get(url), 'Здесь появится ваша переписка')
		response = self.client.post(url, {'text': 'привет'}, **HTMX)
		member = services.find_member(self.ann.profile, self.bob.profile)
		self.assertEqual(response.status_code, 204)
		self.assertEqual(response['HX-Redirect'], reverse('dm-conversation', args=[member.conversation_id]))
		self.assertRedirects(self.client.get(url), reverse('dm-conversation', args=[member.conversation_id]))

		self.client.force_login(self.bob)
		self.assertContains(self.client.get(reverse('index')), 'id="dm-badge-side">1<')
		page = self.client.get(reverse('dm-conversation', args=[member.conversation_id]))
		self.assertContains(page, 'привет')
		self.assertNotContains(page, 'data-flash')  # переписка не попадает в тосты оболочки
		self.assertEqual(services.unread_count(self.bob.profile), 0)

	def test_strangers_get_404(self):
		member, message = services.send_message(self.bob.profile, self.cat.profile, 'не для ann')
		for url in (
			reverse('dm-conversation', args=[member.conversation_id]),
			reverse('dm-updates', args=[member.conversation_id]),
		):
			self.assertEqual(self.client.get(url, **HTMX).status_code, 404)
		self.assertEqual(self.client.post(reverse('dm-send', args=[member.conversation_id]), {'text': 'x'}).status_code, 404)
		self.assertEqual(self.client.post(reverse('dm-delete', args=[member.conversation_id, message.pk])).status_code, 404)


class TypingTests(ConsumerTestCase):
	def setUp(self):
		self.ann, self.bob, self.cat = users('ann', 'bob', 'cat')
		self.member, _ = services.send_message(self.ann.profile, self.bob.profile, 'привет')

	async def connect(self, user):
		client = WebsocketClient(UserConsumer.as_asgi(), user=user)
		await client.connect()
		return client

	async def test_stranger_cannot_spoof(self):
		cat, bob = await self.connect(self.cat), await self.connect(self.bob)
		await cat.send_json({'event': 'typing', 'conversation': self.member.conversation_id})
		await cat.send_json({'event': 'typing', 'conversation': 'x'})
		self.assertTrue(await bob.receive_nothing())
		await cat.disconnect()
		await bob.disconnect()
