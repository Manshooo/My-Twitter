"""Отношения между людьми: подписка, блокировка, заглушение (E3). Одна точка для всех вьюх."""
from django.db import transaction
from django.db.models import Q

from notifications.models import Notification
from notifications.services import notify, retract

from .models import Block, FollowThrough, Mute


def is_blocked_between(a, b):
	"""Есть ли блокировка в любую сторону."""
	return Block.objects.filter(Q(blocker=a, blocked=b) | Q(blocker=b, blocked=a)).exists()


def blocked_profile_ids(profile):
	"""id профилей, с которыми у profile блокировка в любую сторону (подзапрос, а не список)."""
	return Block.objects.filter(blocker=profile).values('blocked').union(
		Block.objects.filter(blocked=profile).values('blocker'),
	)


def follow(follower, followee):
	"""Подписаться. Нельзя на себя и при блокировке в любую сторону. True — подписка есть."""
	if follower.pk == followee.pk or is_blocked_between(follower, followee):
		return False
	FollowThrough.objects.get_or_create(follower=follower, followee=followee)
	notify(followee, follower, Notification.Verb.FOLLOW)
	return True


def unfollow(follower, followee):
	FollowThrough.objects.filter(follower=follower, followee=followee).delete()
	retract(followee, follower, Notification.Verb.FOLLOW)


@transaction.atomic
def block(blocker, blocked):
	if blocker.pk == blocked.pk:
		return
	Block.objects.get_or_create(blocker=blocker, blocked=blocked)
	FollowThrough.objects.filter(Q(follower=blocker, followee=blocked) | Q(follower=blocked, followee=blocker)).delete()


def unblock(blocker, blocked):
	Block.objects.filter(blocker=blocker, blocked=blocked).delete()


def mute(muter, muted):
	if muter.pk != muted.pk:
		Mute.objects.get_or_create(muter=muter, muted=muted)


def unmute(muter, muted):
	Mute.objects.filter(muter=muter, muted=muted).delete()
