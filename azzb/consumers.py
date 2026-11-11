import time

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from dm.realtime import typing_target

from .realtime import user_group

# Код закрытия «не вошёл или забанен»: azzb.js не переподключается.
CLOSE_UNAUTHORIZED = 4401
# «Печатает…» о диалоге — не чаще раза в 2 с; кому слать, перепроверяем раз в минуту (вдруг блокировка).
TYPING_INTERVAL = 2
TYPING_TARGET_TTL = 60


class UserConsumer(AsyncJsonWebsocketConsumer):
	"""Один сокет на вкладку: сигналы из azzb.realtime.push для этого пользователя."""

	group = None

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.typing_sent = {}
		self.typing_targets = {}

	async def connect(self):
		user = self.scope.get('user')
		if user is None or not user.is_authenticated or user.is_banned:
			# Отказ до accept браузер видит как обрыв (1006) и переподключался бы вечно; код виден только после.
			await self.accept()
			await self.close(code=CLOSE_UNAUTHORIZED)
			return
		self.group = user_group(user.pk)
		await self.channel_layer.group_add(self.group, self.channel_name)
		await self.accept()

	async def disconnect(self, code):
		if self.group:
			await self.channel_layer.group_discard(self.group, self.channel_name)

	async def receive_json(self, content, **kwargs):
		"""Сообщения от вкладки; неизвестные молча пропускаем."""
		if isinstance(content, dict) and content.get('event') == 'typing':
			await self.typing(content.get('conversation'))

	async def typing(self, conversation_id):
		if type(conversation_id) is not int or self.group is None:
			return
		now = time.monotonic()
		if now - self.typing_sent.get(conversation_id, -TYPING_INTERVAL) < TYPING_INTERVAL:
			return
		self.typing_sent[conversation_id] = now
		cached = self.typing_targets.get(conversation_id)
		if cached is None or now - cached[1] > TYPING_TARGET_TTL:
			cached = (await typing_target(self.scope['user'].pk, conversation_id), now)
			self.typing_targets[conversation_id] = cached
		if cached[0]:
			await self.channel_layer.group_send(
				user_group(cached[0]), {'type': 'push', 'event': 'typing', 'conversation': conversation_id},
			)

	async def push(self, message):
		await self.send_json({key: value for key, value in message.items() if key != 'type'})
