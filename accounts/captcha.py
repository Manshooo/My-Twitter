"""Yandex SmartCaptcha на регистрации (E2).

Работает, только если в .env заданы SMARTCAPTCHA_CLIENT_KEY и SMARTCAPTCHA_SERVER_KEY
(ключи капчи из консоли Yandex Cloud). Без них — выключена: при разработке и в тестах.
"""
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger('azzb.captcha')

VALIDATE_URL = 'https://smartcaptcha.yandexcloud.net/validate'
TOKEN_FIELD = 'smart-token'


def is_enabled():
	return bool(settings.SMARTCAPTCHA_CLIENT_KEY and settings.SMARTCAPTCHA_SERVER_KEY)


def check(token, ip):
	"""True — человек. Если сервис капчи недоступен, пропускаем (так советует Яндекс):
	лучше пропустить бота, которого остановят лимиты и подтверждение почты, чем закрыть
	регистрацию всем."""
	if not token:
		return False
	data = urllib.parse.urlencode({
		'secret': settings.SMARTCAPTCHA_SERVER_KEY,
		'token': token,
		'ip': ip,
	}).encode()
	try:
		with urllib.request.urlopen(VALIDATE_URL, data=data, timeout=5) as response:
			result = json.load(response)
	except (urllib.error.URLError, TimeoutError, ValueError) as error:
		logger.warning('SmartCaptcha недоступна, пропускаем проверку: %s', error)
		return True
	return result.get('status') == 'ok'
