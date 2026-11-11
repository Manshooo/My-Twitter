"""«Печатает…» (F2): единственное, что вкладка шлёт по сокету. В базу не пишется."""
from channels.db import database_sync_to_async

from .models import Member
from .services import refusal


@database_sync_to_async
def typing_target(user_id, conversation_id):
	"""Кому показать «печатает…»: id пользователя-собеседника или None, если писать ему нельзя."""
	member = (
		Member.objects.filter(conversation_id=conversation_id, profile__user_id=user_id)
		.select_related('profile', 'peer__user', 'conversation')
		.first()
	)
	if member is None or refusal(member.profile, member.peer, member.conversation):
		return None
	return member.peer.user_id
