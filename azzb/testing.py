"""Клиент WebSocket для тестов. channels.testing не годится: он тянет daphne, а у нас uvicorn."""
import json
from datetime import datetime, timezone
from unittest import mock

from asgiref.testing import ApplicationCommunicator
from django.test import TestCase


class ConsumerTestCase(TestCase):
	"""Channels перед каждым сообщением закрывает «устаревшие» соединения с базой, а соединение
	теста внутри транзакции TestCase для него устаревшее — оно закрылось бы посреди теста."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		patcher = mock.patch('channels.db.close_old_connections')
		patcher.start()
		cls.addClassCleanup(patcher.stop)


class WebsocketClient(ApplicationCommunicator):
	def __init__(self, application, path='/ws/', headers=None, user=None):
		scope = {'type': 'websocket', 'path': path, 'query_string': b'', 'headers': headers or [], 'subprotocols': []}
		if user is not None:
			scope['user'] = user
		super().__init__(application, scope)

	async def connect(self, timeout=1):
		"""(True, None) — принято; (False, код) — закрыто."""
		await self.send_input({'type': 'websocket.connect'})
		response = await self.receive_output(timeout)
		if response['type'] == 'websocket.accept' and not await self.receive_nothing(0.05):
			response = await self.receive_output(timeout)
		if response['type'] == 'websocket.close':
			return False, response.get('code', 1000)
		return True, None

	async def send_json(self, data):
		await self.send_input({'type': 'websocket.receive', 'text': json.dumps(data)})

	async def receive_json(self, timeout=1):
		response = await self.receive_output(timeout)
		assert response['type'] == 'websocket.send', response
		return json.loads(response['text'])

	async def disconnect(self, code=1000, timeout=1):
		await self.send_input({'type': 'websocket.disconnect', 'code': code})
		await self.wait(timeout)


# Пользователь тестов — как настоящий: хоть раз входил. Иначе Profile.objects.public() его не покажет.
ACTIVE = {'last_login': datetime(2026, 1, 1, tzinfo=timezone.utc)}
