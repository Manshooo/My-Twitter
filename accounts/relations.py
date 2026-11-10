"""Отношения между людьми: подписка, блокировка, заглушение (E3). Одна точка для всех вьюх."""
from django.db import transaction
from django.db.models import Q

from notifications.models import Notification
from notifications.services import notify, retract

from .models import Block, FollowRequest, FollowThrough, Mute


def is_blocked_between(a, b):
	"""Есть ли блокировка в любую сторону."""
	return Block.objects.filter(Q(blocker=a, blocked=b) | Q(blocker=b, blocked=a)).exists()


def blocked_profile_ids(profile):
	"""id профилей, с которыми у profile блокировка в любую сторону (подзапрос, а не список)."""
	return Block.objects.filter(blocker=profile).values('blocked').union(
		Block.objects.filter(blocked=profile).values('blocker'),
	)


FOLLOWING, REQUESTED = 'following', 'requested'


def follow(follower, followee):
	"""Подписаться. Нельзя на себя и при блокировке в любую сторону. На закрытый аккаунт (E5) —
	заявка, подписку создаст одобрение. Возвращает FOLLOWING, REQUESTED или None (нельзя)."""
	if follower.pk == followee.pk or is_blocked_between(follower, followee):
		return None
	if FollowThrough.objects.filter(follower=follower, followee=followee).exists():
		return FOLLOWING
	if followee.is_private:
		_, created = FollowRequest.objects.get_or_create(requester=follower, target=followee)
		if created:
			notify(followee, follower, Notification.Verb.FOLLOW_REQUEST)
		return REQUESTED
	FollowThrough.objects.get_or_create(follower=follower, followee=followee)
	notify(followee, follower, Notification.Verb.FOLLOW)
	return FOLLOWING


def unfollow(follower, followee):
	"""Отписаться или отозвать заявку."""
	FollowThrough.objects.filter(follower=follower, followee=followee).delete()
	retract(followee, follower, Notification.Verb.FOLLOW)
	cancel_request(follower, followee)


def cancel_request(requester, target):
	FollowRequest.objects.filter(requester=requester, target=target).delete()
	retract(target, requester, Notification.Verb.FOLLOW_REQUEST)


@transaction.atomic
def approve_request(target, requester):
	"""Одобрить заявку: появляется подписка, автор заявки узнаёт об этом. False — заявки нет."""
	deleted, _ = FollowRequest.objects.filter(requester=requester, target=target).delete()
	if not deleted:
		return False
	retract(target, requester, Notification.Verb.FOLLOW_REQUEST)
	FollowThrough.objects.get_or_create(follower=requester, followee=target)
	notify(requester, target, Notification.Verb.FOLLOW_ACCEPTED)
	return True


def decline_request(target, requester):
	"""Отклонить заявку. Автору заявки ничего не сообщаем: она просто пропадает."""
	cancel_request(requester, target)


@transaction.atomic
def set_private(profile, private):
	"""Закрыть или открыть аккаунт. При открытии все ждущие заявки одобряются: закрывать
	больше нечего, а люди хотели подписаться."""
	profile.is_private = private
	profile.save(update_fields=['is_private'])
	if not private:
		for request in FollowRequest.objects.filter(target=profile).select_related('requester'):
			approve_request(profile, request.requester)


def remove_follower(profile, follower):
	"""Убрать подписчика (нужно прежде всего закрытым аккаунтам): подписка снимается молча."""
	FollowThrough.objects.filter(follower=follower, followee=profile).delete()
	retract(profile, follower, Notification.Verb.FOLLOW)


@transaction.atomic
def block(blocker, blocked):
	if blocker.pk == blocked.pk:
		return
	Block.objects.get_or_create(blocker=blocker, blocked=blocked)
	FollowThrough.objects.filter(Q(follower=blocker, followee=blocked) | Q(follower=blocked, followee=blocker)).delete()
	FollowRequest.objects.filter(Q(requester=blocker, target=blocked) | Q(requester=blocked, target=blocker)).delete()


def unblock(blocker, blocked):
	Block.objects.filter(blocker=blocker, blocked=blocked).delete()


def mute(muter, muted):
	if muter.pk != muted.pk:
		Mute.objects.get_or_create(muter=muter, muted=muted)


def unmute(muter, muted):
	Mute.objects.filter(muter=muter, muted=muted).delete()
