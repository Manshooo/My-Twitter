from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model

from azzb.testing import ACTIVE

from . import realtime
from .asgi import application
from .consumers import CLOSE_UNAUTHORIZED, UserConsumer
from .testing import ConsumerTestCase, WebsocketClient

User = get_user_model()


class RealtimeTests(ConsumerTestCase):
	def setUp(self):
		self.ann = User.objects.create_user('ann', 'ann@example.com', 'pass-12345', **ACTIVE)

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

	async def test_foreign_origin_is_refused(self):
		communicator = WebsocketClient(application, headers=[(b'origin', b'https://evil.example')])
		connected, _ = await communicator.connect()
		self.assertFalse(connected)

	async def test_guest_through_full_stack_is_refused(self):
		communicator = WebsocketClient(application, headers=[(b'origin', b'https://azzb.ru')])
		connected, code = await communicator.connect()
		self.assertFalse(connected)
		self.assertEqual(code, CLOSE_UNAUTHORIZED)
