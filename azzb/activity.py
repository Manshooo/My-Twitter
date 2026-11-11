"""Запись в журнал действий (ActivityRecord, см. azzb/retention.py). Вход и регистрация пишутся
сигналами ниже, публикация, правка и удаление — вызовом record() из вьюх."""
import ipaddress

from allauth.account.signals import email_changed, password_changed, password_reset, user_signed_up
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.db import transaction
from django.db.models import Q
from django.dispatch import receiver

from accounts import devices

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
	if request is None:
		return
	entry = record(request, Action.LOGIN, user=user)
	if user.email and devices.is_new_device(user, entry.user_agent, entry.created_at):
		message = devices.new_device_email(request, user, entry)
		transaction.on_commit(lambda: devices.send_quietly(message))


@receiver(user_login_failed)
def record_login_failed(sender, credentials, request=None, **kwargs):
	"""Только для существующих аккаунтов: в поле логина по ошибке вводят и пароли — их не пишем."""
	login = credentials.get('username') or credentials.get('email') or ''
	if request is None or not login:
		return
	user = get_user_model().objects.filter(Q(username__iexact=login) | Q(email__iexact=login)).first()
	if user is not None:
		record(request, Action.LOGIN_FAILED, user=user)


@receiver(password_changed)
def record_password_change(sender, request, user, **kwargs):
	record(request, Action.PASSWORD_CHANGE, user=user)


@receiver(password_reset)
def record_password_reset(sender, request, user, **kwargs):
	record(request, Action.PASSWORD_RESET, user=user)


@receiver(email_changed)
def record_email_change(sender, request, user, **kwargs):
	record(request, Action.EMAIL_CHANGE, user=user)


@receiver(user_signed_up)
def record_signup(sender, request, user, **kwargs):
	if request is not None:
		record(request, Action.SIGNUP, user=user)
