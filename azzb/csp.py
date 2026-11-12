"""Content-Security-Policy: браузер выполняет только скрипты, которые подключили мы сами. Даже если
в текст поста проскочит <script>, он не запустится.

Скрипты — по nonce и 'strict-dynamic' (рекомендация Lighthouse «CSP против XSS»): у каждого <script>
в шаблоне атрибут nonce="{{ request.csp_nonce }}", новое случайное значение на каждый ответ.
Скрипты, которые добавляют они сами (Метрика, SmartCaptcha, в будущем — реклама), разрешены без
перечисления хостов: белый список хостов обходится, если на разрешённом хосте найдётся
JSONP или старая библиотека, а у nonce такой лазейки нет. Список хостов в script-src остался для
браузеров без 'strict-dynamic' — новые его игнорируют.

Стилям нужен 'unsafe-inline': в шаблонах много style="...", а htmx вставляет свой <style>.
Инлайн-скриптов в шаблонах нет, eval у htmx выключен, скрипты из подгруженного HTML htmx не
исполняет (htmx-config в head.html): иначе 'strict-dynamic' разрешил бы их как созданные htmx.
При DEBUG заголовок только сообщает о нарушениях в консоль: debug toolbar вставляет инлайн-скрипт.

Trusted Types не включаем: htmx вставляет ответы через innerHTML, рекламные скрипты — тоже.
"""
import secrets

from django.conf import settings

# Метрика загружается, только если посетитель разрешил аналитику; SmartCaptcha — на странице регистрации.
METRIKA = ('https://mc.yandex.ru', 'https://mc.yandex.com', 'https://yastatic.net')
CAPTCHA = ('https://smartcaptcha.yandexcloud.net',)


class Nonce:
	"""nonce ответа. Помнит, выводил ли его шаблон: страницы без него (админка Django — её <script>
	мы не правим) получают политику без nonce и 'strict-dynamic', иначе их скрипты не запустятся."""

	def __init__(self):
		self.value = secrets.token_urlsafe(18)
		self.used = False

	def __str__(self):
		self.used = True
		return self.value


def build_policy(request, nonce=None):
	host = request.get_host()
	scripts = (f"'nonce-{nonce}'", "'strict-dynamic'") if nonce else ()
	directives = {
		'default-src': ("'self'",),
		'script-src': (*scripts, "'self'", *METRIKA, *CAPTCHA),
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
		# Шаблоны берут nonce из request; страница 500 рендерится без request — на ней скрипты не нужны.
		nonce = request.csp_nonce = Nonce()
		response = self.get_response(request)
		if response.get('Content-Type', '').startswith('text/html'):
			response.setdefault(self.header, build_policy(request, nonce.value if nonce.used else None))
		return response
