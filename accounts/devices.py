"""Устройства и сеансы: что показать человеку о его входах и когда предупредить о входе с нового устройства.

Сеансы ведёт allauth.usersessions (UserSession: IP, User-Agent, начало, последняя активность). Отпечатков
браузера (экран, шрифты, часовой пояс) не собираем: для безопасности хватает браузера, системы и IP.
"""
import logging
from datetime import timedelta
from functools import lru_cache
from time import time

from allauth.account.adapter import get_adapter
from allauth.usersessions.models import UserSession
from django.urls import reverse
from django.utils import timezone
from ua_parser import parse

from azzb.models import ActivityRecord

logger = logging.getLogger(__name__)

# Последняя активность сеанса — с точностью до 5 минут: иначе запись в базу на каждый запрос.
SEEN_INTERVAL = 300
SEEN_SESSION_KEY = 'azzb_seen_at'
# Устройство «новое», если с него не входили и не регистрировались за этот срок.
KNOWN_DEVICE_WINDOW = timedelta(days=365)

BROWSERS = {
	'Chrome Mobile': 'Chrome', 'Chrome Mobile iOS': 'Chrome', 'Chrome Mobile WebView': 'Chrome',
	'Mobile Safari': 'Safari', 'Mobile Safari UI/WKWebView': 'Safari',
	'Firefox Mobile': 'Firefox', 'Firefox iOS': 'Firefox',
	'Yandex Browser': 'Яндекс Браузер', 'Edge Mobile': 'Edge',
	'Samsung Internet': 'Samsung Internet', 'Opera Mobile': 'Opera',
}
SYSTEMS = {'Mac OS X': 'macOS', 'Chrome OS': 'ChromeOS'}


@lru_cache(maxsize=1024)
def device(user_agent):
	"""(браузер, система) по User-Agent; None — не распознано."""
	result = parse(user_agent or '')
	browser = result.user_agent.family if result.user_agent else None
	system = result.os.family if result.os else None
	if result.device and result.device.family in ('iPhone', 'iPad'):
		system = result.device.family
	browser = BROWSERS.get(browser, browser) if browser not in (None, 'Other') else None
	system = SYSTEMS.get(system, system) if system not in (None, 'Other') else None
	return browser, system


def describe(user_agent):
	browser, system = device(user_agent)
	if browser and system:
		return f'{browser}, {system}'
	return browser or system or 'Неизвестное устройство'


def touch_session(request):
	"""Создать или обновить запись сеанса не чаще раза в SEEN_INTERVAL. Заодно появляются
	сеансы, начатые до того, как их стали записывать."""
	session = getattr(request, 'session', None)
	if session is None or not session.session_key:
		return
	seen = session.get(SEEN_SESSION_KEY, 0)
	if time() - seen < SEEN_INTERVAL:
		return
	session[SEEN_SESSION_KEY] = int(time())
	UserSession.objects.create_from_request(request)


def sessions(request):
	"""Активные сеансы, текущий — первым."""
	current = request.session.session_key
	items = UserSession.objects.purge_and_list(request.user)
	items.sort(key=lambda session: (session.session_key != current, -session.last_seen_at.timestamp()))
	for session in items:
		session.current = session.session_key == current
		session.title = describe(session.user_agent)
	return items


def is_new_device(user, user_agent, before):
	"""Вход с браузера и системы, с которых человек не входил за KNOWN_DEVICE_WINDOW.
	Первый вход после регистрации новым не считается: устройство регистрации уже известно."""
	known = (
		ActivityRecord.objects
		.filter(user=user, action__in=[ActivityRecord.Action.LOGIN, ActivityRecord.Action.SIGNUP])
		.filter(created_at__gte=timezone.now() - KNOWN_DEVICE_WINDOW, created_at__lt=before)
		.values_list('user_agent', flat=True)[:200]
	)
	known = list(known)
	if not known:
		return False
	current = device(user_agent)
	return all(device(agent) != current for agent in known)


def new_device_email(request, user, record):
	"""Письмо собирается, пока есть запрос (адрес сайта, ссылки), а уходит после коммита."""
	return get_adapter(request).render_mail('account/email/new_device', user.email, {
		'user': user,
		'device': describe(record.user_agent),
		'ip': record.ip or 'не определён',
		'when': timezone.localtime(record.created_at),
		'settings_url': request.build_absolute_uri(reverse('account-settings') + '#devices'),
		'password_url': request.build_absolute_uri(reverse('account_change_password')),
	})


def send_quietly(message):
	# Письмо о входе — не повод ронять сам вход, если почтовый сервер недоступен.
	try:
		message.send()
	except Exception:
		logger.warning('Не удалось отправить письмо о новом устройстве', exc_info=True)
