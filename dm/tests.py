import io
import json
import shutil
import tempfile
import zipfile
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image as PILImage

from accounts import relations
from accounts.account import erase_account
from accounts.models import DmPolicy
from azzb.consumers import UserConsumer
from azzb.retention import RETENTION_CONTENT, purge_expired
from azzb.testing import ConsumerTestCase, WebsocketClient

from . import services
from .models import Conversation, Member, Message, MessageImage

User = get_user_model()
MEDIA_ROOT = tempfile.mkdtemp(prefix='azzb-test-dm-')
HTMX = {'HTTP_HX_REQUEST': 'true'}


def tearDownModule():
	shutil.rmtree(MEDIA_ROOT, ignore_errors=True)


def make_upload(name='photo.png'):
	buffer = io.BytesIO()
	PILImage.new('RGB', (40, 30), (20, 120, 120)).save(buffer, 'PNG')
	return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/png')


def users(*names):
	return [User.objects.create_user(name, f'{name}@example.com', 'pass-12345') for name in names]


class RulesTests(TestCase):
	def setUp(self):
		self.ann, self.bob = users('ann', 'bob')
		self.a, self.b = self.ann.profile, self.bob.profile

	def set_policy(self, profile, policy):
		profile.dm_policy = policy
		profile.save(update_fields=['dm_policy'])

	def test_everyone_by_default(self):
		self.assertIsNone(services.refusal(self.a, self.b))
		self.assertEqual(services.refusal(self.a, self.a), 'Себе написать нельзя.')

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

	def test_deleted_and_banned(self):
		self.bob.banned_until = timezone.now() + timedelta(days=1)
		self.bob.save()
		self.assertIn('нельзя написать', services.refusal(self.a, self.b))
		self.bob.banned_until = None
		self.bob.deleted_at = timezone.now()
		self.bob.is_active = False
		self.bob.save()
		self.assertEqual(services.refusal(self.a, self.b), 'Аккаунт удалён.')

	def test_send_refused_raises(self):
		self.set_policy(self.b, DmPolicy.NOBODY)
		with self.assertRaises(ValidationError):
			services.send_message(self.a, self.b, 'привет')
		self.assertFalse(Conversation.objects.exists())

	def test_empty_and_long(self):
		with self.assertRaises(ValidationError):
			services.send_message(self.a, self.b, '   ')
		with self.assertRaises(ValidationError):
			services.send_message(self.a, self.b, 'я' * 2001)


class ConversationTests(TestCase):
	def setUp(self):
		self.ann, self.bob, self.cat = users('ann', 'bob', 'cat')
		self.a, self.b, self.c = self.ann.profile, self.bob.profile, self.cat.profile

	def test_one_conversation_per_pair_and_signals(self):
		with mock.patch('dm.services.push') as push:
			member, first = services.send_message(self.a, self.b, 'привет')
		push.assert_called_once_with([self.bob.pk, self.ann.pk], 'dm', conversation=member.conversation_id)
		services.send_message(self.b, self.a, 'и тебе', member=services.find_member(self.b, self.a))
		self.assertEqual(Conversation.objects.count(), 1)
		self.assertEqual(Member.objects.count(), 2)
		self.assertEqual(Conversation.objects.get().last_message_at, Message.objects.latest('pk').created_at)

	def test_unread_and_read(self):
		services.send_message(self.a, self.b, 'раз')
		services.send_message(self.a, self.b, 'два', member=services.find_member(self.a, self.b))
		self.assertEqual(services.unread_count(self.b), 1)
		self.assertEqual(services.unread_count(self.a), 0)  # свои не считаются
		bob_side = services.find_member(self.b, self.a)
		with mock.patch('dm.services.push') as push:
			self.assertTrue(services.mark_read(bob_side))
		push.assert_any_call([self.ann.pk], 'dm-read', conversation=bob_side.conversation_id)
		self.assertEqual(services.unread_count(self.b), 0)
		self.assertFalse(services.mark_read(bob_side))
		ann_side = services.find_member(self.a, self.b)
		messages, _ = services.page(ann_side)
		self.assertEqual(services.seen_by_peer(ann_side, messages), messages[-1])
		services.send_message(self.b, self.a, 'ответ', member=bob_side)
		self.assertIsNone(services.seen_by_peer(ann_side, services.page(ann_side)[0]))

	def test_clear_hides_until_new_message(self):
		services.send_message(self.a, self.b, 'старое')
		bob_side = services.find_member(self.b, self.a)
		services.clear_conversation(bob_side)
		bob_side.refresh_from_db()
		self.assertEqual(services.inbox(self.b)[0], [])
		self.assertEqual(services.unread_count(self.b), 0)
		self.assertEqual(len(services.inbox(self.a)[0]), 1)  # у собеседника осталось
		services.send_message(self.a, self.b, 'новое', member=services.find_member(self.a, self.b))
		self.assertEqual(len(services.inbox(self.b)[0]), 1)
		self.assertEqual([m.text for m in services.page(bob_side)[0]], ['новое'])

	def test_inbox_order_and_preview(self):
		services.send_message(self.a, self.b, 'bob')
		services.send_message(self.a, self.c, 'cat')
		items, _ = services.inbox(self.a)
		self.assertEqual([item.peer for item in items], [self.c, self.b])
		self.assertEqual(items[0].last_message.text, 'cat')

	def test_paging(self):
		member, _ = services.send_message(self.a, self.b, '0')
		for index in range(1, 35):
			services.send_message(self.a, self.b, str(index), member=member)
		page, has_more = services.page(member)
		self.assertTrue(has_more)
		self.assertEqual(page[-1].text, '34')
		older, more = services.page(member, before=page[0].pk)
		self.assertFalse(more)
		self.assertEqual([m.text for m in older], [str(i) for i in range(5)])
		self.assertEqual(services.newer(member, page[-2].pk), [page[-1]])

	def test_delete_only_own(self):
		member, message = services.send_message(self.a, self.b, 'секрет')
		self.assertFalse(services.delete_message(services.find_member(self.b, self.a), message.pk))
		self.assertTrue(services.delete_message(member, message.pk))
		message.refresh_from_db()
		self.assertIsNotNone(message.deleted_at)
		self.assertEqual(message.text, 'секрет')  # стирается по сроку хранения

	@override_settings(MEDIA_ROOT=MEDIA_ROOT)
	def test_images_are_stored_and_purged(self):
		_, message = services.send_message(self.a, self.b, '', [make_upload()])
		image = message.images.get()
		self.assertTrue(image.file.name.endswith('.webp'))
		storage, name = image.file.storage, image.file.name
		self.assertTrue(storage.exists(name))
		with self.captureOnCommitCallbacks(execute=True):
			services.purge_messages(Message.objects.filter(pk=message.pk))
		self.assertFalse(storage.exists(name))
		message.refresh_from_db()
		self.assertIsNotNone(message.purged_at)


class RetentionTests(TestCase):
	def setUp(self):
		self.ann, self.bob = users('ann', 'bob')

	def test_purge_expired_erases_old_deleted_messages(self):
		member, old = services.send_message(self.ann.profile, self.bob.profile, 'старое')
		_, fresh = services.send_message(self.ann.profile, self.bob.profile, 'свежее', member=member)
		Message.objects.filter(pk=old.pk).update(deleted_at=timezone.now() - RETENTION_CONTENT - timedelta(days=1))
		Message.objects.filter(pk=fresh.pk).update(deleted_at=timezone.now())
		self.assertEqual(purge_expired()['messages'], 1)
		old.refresh_from_db()
		fresh.refresh_from_db()
		self.assertEqual(old.text, '')
		self.assertEqual(fresh.text, 'свежее')

	def test_erase_account_purges_sent_messages(self):
		services.send_message(self.ann.profile, self.bob.profile, 'от ann')
		services.send_message(self.bob.profile, self.ann.profile, 'от bob', member=services.find_member(self.bob.profile, self.ann.profile))
		erase_account(self.ann)
		self.assertEqual(Message.objects.get(sender=self.ann.profile).text, '')
		self.assertEqual(Message.objects.get(sender=self.bob.profile).text, 'от bob')
		self.assertFalse(Member.objects.filter(profile=self.ann.profile).exists())
		self.assertEqual(len(services.inbox(self.bob.profile)[0]), 1)

	def test_export_contains_conversations(self):
		services.send_message(self.ann.profile, self.bob.profile, 'для архива')
		self.client.force_login(self.ann)
		response = self.client.post(reverse('account-export'))
		with zipfile.ZipFile(io.BytesIO(b''.join(response.streaming_content))) as bundle:
			data = json.loads(bundle.read('data.json'))
		self.assertEqual(data['conversations'][0]['with'], 'bob')
		self.assertEqual(data['conversations'][0]['messages'][0]['text'], 'для архива')
		self.assertEqual(data['conversations'][0]['messages'][0]['from'], 'me')


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

	def test_send_and_updates(self):
		member, first = services.send_message(self.ann.profile, self.bob.profile, 'первое')
		response = self.client.post(reverse('dm-send', args=[member.conversation_id]), {'text': 'второе'}, **HTMX)
		self.assertEqual(response.status_code, 204)
		self.assertIn('azzb:dm-sent', response['HX-Trigger'])
		updates = self.client.get(reverse('dm-updates', args=[member.conversation_id]), {'after': first.pk}, **HTMX)
		self.assertContains(updates, 'второе')
		self.assertNotContains(updates, 'первое')
		self.assertContains(updates, 'id="dm-seen" hx-swap-oob="true" hidden')

	def test_send_errors(self):
		member, _ = services.send_message(self.ann.profile, self.bob.profile, 'первое')
		response = self.client.post(reverse('dm-send', args=[member.conversation_id]), {'text': ''}, **HTMX)
		self.assertEqual(response.status_code, 400)
		self.assertIn('Напишите', response.json()['errors'][0])
		relations.block(self.bob.profile, self.ann.profile)
		response = self.client.post(reverse('dm-send', args=[member.conversation_id]), {'text': 'эй'}, **HTMX)
		self.assertEqual(response.status_code, 400)
		self.assertContains(self.client.get(reverse('dm-conversation', args=[member.conversation_id])), 'нельзя написать')

	@override_settings(MEDIA_ROOT=MEDIA_ROOT)
	def test_send_image(self):
		member, _ = services.send_message(self.ann.profile, self.bob.profile, 'первое')
		response = self.client.post(reverse('dm-send', args=[member.conversation_id]), {'images': [make_upload()]}, **HTMX)
		self.assertEqual(response.status_code, 204)
		self.assertEqual(MessageImage.objects.count(), 1)

	def test_strangers_get_404(self):
		member, message = services.send_message(self.bob.profile, self.cat.profile, 'не для ann')
		for url in (
			reverse('dm-conversation', args=[member.conversation_id]),
			reverse('dm-updates', args=[member.conversation_id]),
		):
			self.assertEqual(self.client.get(url, **HTMX).status_code, 404)
		self.assertEqual(self.client.post(reverse('dm-send', args=[member.conversation_id]), {'text': 'x'}).status_code, 404)
		self.assertEqual(self.client.post(reverse('dm-delete', args=[member.conversation_id, message.pk])).status_code, 404)

	def test_delete_and_clear(self):
		member, message = services.send_message(self.ann.profile, self.bob.profile, 'удалю')
		response = self.client.post(reverse('dm-delete', args=[member.conversation_id, message.pk]), **HTMX)
		self.assertContains(response, 'Сообщение удалено')
		self.assertRedirects(self.client.post(reverse('dm-clear', args=[member.conversation_id])), reverse('dm-inbox'))
		self.assertContains(self.client.get(reverse('dm-inbox')), 'Диалогов пока нет')

	def test_inbox_fragment(self):
		services.send_message(self.bob.profile, self.ann.profile, 'привет ann')
		self.assertContains(self.client.get(reverse('dm-inbox')), 'привет ann')
		fragment = self.client.get(reverse('dm-inbox'), **HTMX)
		self.assertContains(fragment, 'dm-item nu unread')
		self.assertNotContains(fragment, '<html')

	def test_profile_button_and_policy_setting(self):
		self.assertContains(self.client.get(reverse('profile', args=['bob'])), reverse('dm-start', args=['bob']))
		self.client.force_login(self.bob)
		self.client.post(reverse('edit-profile'), {'username': 'bob', 'theme': '', 'dm_policy': 'nobody'})
		self.bob.profile.refresh_from_db()
		self.assertEqual(self.bob.profile.dm_policy, DmPolicy.NOBODY)
		self.client.force_login(self.ann)
		self.assertNotContains(self.client.get(reverse('profile', args=['bob'])), reverse('dm-start', args=['bob']))
		self.assertEqual(self.client.post(reverse('dm-start', args=['bob']), {'text': 'x'}, **HTMX).status_code, 400)


class TypingTests(ConsumerTestCase):
	def setUp(self):
		self.ann, self.bob, self.cat = users('ann', 'bob', 'cat')
		self.member, _ = services.send_message(self.ann.profile, self.bob.profile, 'привет')

	async def connect(self, user):
		client = WebsocketClient(UserConsumer.as_asgi(), user=user)
		await client.connect()
		return client

	async def test_typing_reaches_peer_only(self):
		ann, bob = await self.connect(self.ann), await self.connect(self.bob)
		await ann.send_json({'event': 'typing', 'conversation': self.member.conversation_id})
		self.assertEqual(await bob.receive_json(), {'event': 'typing', 'conversation': self.member.conversation_id})
		self.assertTrue(await ann.receive_nothing())
		# Второй сигнал сразу за первым не шлётся.
		await ann.send_json({'event': 'typing', 'conversation': self.member.conversation_id})
		self.assertTrue(await bob.receive_nothing())
		await ann.disconnect()
		await bob.disconnect()

	async def test_stranger_cannot_spoof(self):
		cat, bob = await self.connect(self.cat), await self.connect(self.bob)
		await cat.send_json({'event': 'typing', 'conversation': self.member.conversation_id})
		await cat.send_json({'event': 'typing', 'conversation': 'x'})
		self.assertTrue(await bob.receive_nothing())
		await cat.disconnect()
		await bob.disconnect()

