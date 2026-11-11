"""Content-Security-Policy: браузер выполняет скрипты только с сайта и от тех сторонних сервисов,
которые мы подключаем сами. Даже если в текст поста проскочит <script>, он не запустится.

Стилям нужен 'unsafe-inline': в шаблонах много style="...", а htmx вставляет свой <style>.
Скриптам — нет: инлайн-скриптов в шаблонах нет, а eval у htmx выключен (htmx-config в head.html).
При DEBUG заголовок только сообщает о нарушениях в консоль: debug toolbar вставляет инлайн-скрипт.
"""
from django.conf import settings

# Метрика загружается, только если посетитель разрешил аналитику; SmartCaptcha — на странице регистрации.
METRIKA = ('https://mc.yandex.ru', 'https://mc.yandex.com', 'https://yastatic.net')
CAPTCHA = ('https://smartcaptcha.yandexcloud.net',)


def build_policy(request):
	host = request.get_host()
	directives = {
		'default-src': ("'self'",),
		'script-src': ("'self'", *METRIKA, *CAPTCHA),
		'style-src': ("'self'", "'unsafe-inline'"),
		'img-src': ("'self'", 'data:', 'blob:', *METRIKA),
		'font-src': ("'self'",),
		# 'self' покрывает wss:// не во всех браузерах — адрес сокета указан явно.
		'connect-src': ("'self'", f'wss://{host}', f'ws://{host}' if settings.DEBUG else '', *METRIKA, *CAPTCHA),
		'frame-src': (*CAPTCHA, *METRIKA),
		'worker-src': ("'self'",),
		'manifest-src': ("'self'",),
		'object-src': ("'none'",),
		'base-uri': ("'self'",),
		'form-action': ("'self'",),
		'frame-ancestors': ("'none'",),
	}
	return '; '.join(f"{name} {' '.join(source for source in sources if source)}" for name, sources in directives.items())


class ContentSecurityPolicyMiddleware:
	def __init__(self, get_response):
		self.get_response = get_response
		self.header = 'Content-Security-Policy-Report-Only' if settings.DEBUG else 'Content-Security-Policy'

	def __call__(self, request):
		response = self.get_response(request)
		if response.get('Content-Type', '').startswith('text/html'):
			response.setdefault(self.header, build_policy(request))
		return response
