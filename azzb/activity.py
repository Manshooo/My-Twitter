"""Запись в журнал действий (ActivityRecord, 149-ФЗ ст. 10.1). Вход и регистрация пишутся
сигналами ниже, публикация, правка и удаление — вызовом record() из вьюх."""
import ipaddress

from allauth.account.signals import user_signed_up
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .models import ActivityRecord
from .ratelimit import client_ip

Action = ActivityRecord.Action


def _ip(request):
	ip = client_ip(request)
	try:
		ipaddress.ip_address(ip)
	except ValueError:
		return None
	return None if ip == '0.0.0.0' else ip


def record(request, action, user=None, post=None):
	"""Записать действие. user — по умолчанию тот, кто делает запрос."""
	user = user or request.user
	return ActivityRecord.objects.create(
		action=action,
		user=user,
		username=user.username,
		email=user.email,
		post_id=getattr(post, 'pk', None),
		ip=_ip(request),
		user_agent=request.headers.get('User-Agent', '')[:400],
	)


@receiver(user_logged_in)
def record_login(sender, request, user, **kwargs):
	# login() можно вызвать и без запроса — тогда записывать нечего.
	if request is not None:
		record(request, Action.LOGIN, user=user)


@receiver(user_signed_up)
def record_signup(sender, request, user, **kwargs):
	if request is not None:
		record(request, Action.SIGNUP, user=user)
