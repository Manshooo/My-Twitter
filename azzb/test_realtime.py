from datetime import timedelta
from unittest import mock

from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import realtime
from .asgi import application
from .consumers import CLOSE_UNAUTHORIZED, UserConsumer
from .testing import ConsumerTestCase, WebsocketClient

User = get_user_model()


class RealtimeTests(ConsumerTestCase):
	def setUp(self):
		self.ann = User.objects.create_user('ann', 'ann@example.com', 'pass-12345')

	async def connect(self, user):
		communicator = WebsocketClient(UserConsumer.as_asgi(), user=user)
		connected, code = await communicator.connect()
		return communicator, connected, code

	async def test_signal_reaches_every_tab_of_the_user(self):
		first, connected, _ = await self.connect(self.ann)
		self.assertTrue(connected)
		second, _, _ = await self.connect(self.ann)
		await get_channel_layer().group_send(realtime.user_group(self.ann.pk), {'type': 'push', 'event': 'badges'})
		self.assertEqual(await first.receive_json(), {'event': 'badges'})
		self.assertEqual(await second.receive_json(), {'event': 'badges'})
		await first.disconnect()
		await second.disconnect()

	async def test_guest_and_banned_are_refused(self):
		_, connected, code = await self.connect(AnonymousUser())
		self.assertFalse(connected)
		self.assertEqual(code, CLOSE_UNAUTHORIZED)
		self.ann.banned_until = timezone.now() + timedelta(days=1)
		_, connected, code = await self.connect(self.ann)
		self.assertFalse(connected)
		self.assertEqual(code, CLOSE_UNAUTHORIZED)

	async def test_foreign_origin_is_refused(self):
		communicator = WebsocketClient(application, headers=[(b'origin', b'https://evil.example')])
		connected, _ = await communicator.connect()
		self.assertFalse(connected)

	async def test_guest_through_full_stack_is_refused(self):
		communicator = WebsocketClient(application, headers=[(b'origin', b'https://azzb.ru')])
		connected, code = await communicator.connect()
		self.assertFalse(connected)
		self.assertEqual(code, CLOSE_UNAUTHORIZED)

	def test_push_waits_for_commit(self):
		with mock.patch.object(realtime, '_send') as send:
			with self.captureOnCommitCallbacks() as callbacks:
				realtime.push([self.ann.pk, None], 'badges')
			send.assert_not_called()
			for callback in callbacks:
				callback()
		send.assert_called_once_with({self.ann.pk}, {'type': 'push', 'event': 'badges'})

	def test_broken_redis_does_not_break_the_request(self):
		layer = mock.Mock()
		layer.group_send = mock.AsyncMock(side_effect=ConnectionError)
		with mock.patch.object(realtime, 'get_channel_layer', return_value=layer), self.assertLogs('azzb.realtime', 'WARNING'):
			realtime._send({self.ann.pk}, {'type': 'push', 'event': 'badges'})

	def test_socket_path_only_when_enabled(self):
		self.client.force_login(self.ann)
		with override_settings(REALTIME_WS=False):
			self.assertNotContains(self.client.get(reverse('index')), 'data-ws-path')
		with override_settings(REALTIME_WS=True):
			self.assertContains(self.client.get(reverse('index')), 'data-ws-path="/ws/"')


class RedisLayerConfigTests(SimpleTestCase):
	def test_read_timeout_outlives_layer_wait(self):
		from channels_redis.core import RedisChannelLayer

		from azzb.settings import redis_channel_layer

		host = redis_channel_layer('redis://127.0.0.1:6379/0')['CONFIG']['hosts'][0]
		# Иначе redis-py обрывает ожидание сообщения раньше channels_redis, и сокет закрывается.
		self.assertGreater(host['socket_timeout'], RedisChannelLayer.brpop_timeout)
		self.assertLess(host['socket_connect_timeout'], 5)
