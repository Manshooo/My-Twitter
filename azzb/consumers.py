from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .realtime import user_group

# Код закрытия «не вошёл или забанен»: azzb.js не переподключается.
CLOSE_UNAUTHORIZED = 4401


class UserConsumer(AsyncJsonWebsocketConsumer):
	"""Один сокет на вкладку: сигналы из azzb.realtime.push для этого пользователя."""

	group = None

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
		"""Сообщения от вкладки. Пока их нет; неизвестные молча пропускаем."""

	async def push(self, message):
		await self.send_json({key: value for key, value in message.items() if key != 'type'})
