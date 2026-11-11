"""Сигналы в открытые вкладки по WebSocket (F1).

По сокету идёт только «что изменилось» ({"event": "badges"}, {"event": "dm", ...}), а сами данные
вкладка забирает обычным HTTP-запросом. Права проверяет одна точка — вьюха, и пропущенный сигнал
(сокет переподключался) ничего не ломает: после подключения вкладка один раз обновляет всё сама.
"""
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

logger = logging.getLogger('azzb.realtime')


def user_group(user_id):
	"""Группа всех вкладок одного пользователя (id CustomUser, не Profile)."""
	return f'user.{user_id}'


def _send(user_ids, message):
	layer = get_channel_layer()
	if layer is None:
		return
	try:
		for user_id in user_ids:
			async_to_sync(layer.group_send)(user_group(user_id), message)
	except Exception:
		# Redis недоступен — запрос пользователя всё равно должен пройти; вкладки догонят опросом.
		logger.warning('Не удалось отправить сигнал %s', message.get('event'), exc_info=True)


def push(user_ids, event, **data):
	"""Отправить сигнал вкладкам пользователей после коммита: раньше вкладка спросила бы
	ещё не записанное."""
	user_ids = {user_id for user_id in user_ids if user_id}
	if not user_ids:
		return
	message = {'type': 'push', 'event': event, **data}
	transaction.on_commit(lambda: _send(user_ids, message))

