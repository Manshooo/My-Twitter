"""Мелочи для HTMX: распознать запрос, ответить ошибкой, передать событие в браузер."""
import json
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.http import JsonResponse
from django.utils.cache import patch_vary_headers


def is_htmx(request):
	return request.headers.get('HX-Request') == 'true'


def htmx_errors(messages, status=400):
	"""Ошибки для composer и тостов: {"errors": [...]} — их показывает azzb.js."""
	if isinstance(messages, str):
		messages = [messages]
	return JsonResponse({'errors': list(messages)}, status=status)


def trigger(response, events):
	"""События для браузера в заголовке HX-Trigger: htmx вызовет их на странице.
	json.dumps экранирует кириллицу (\\uXXXX) — заголовки HTTP могут быть только ASCII."""
	response['HX-Trigger'] = json.dumps(events)
	return response


def htmx_login_required(view):
	"""Как login_required, но HTMX-запросу отвечает 401, а не редиректом:
	htmx молча прошёл бы по редиректу и вставил страницу входа вместо карточки."""
	@wraps(view)
	def wrapper(request, *args, **kwargs):
		if request.user.is_authenticated:
			return view(request, *args, **kwargs)
		if is_htmx(request):
			return htmx_errors('Сессия закончилась. Войдите заново.', status=401)
		return redirect_to_login(request.get_full_path())
	return wrapper


class HtmxVaryMiddleware:
	"""Одна и та же лента отдаётся целиком или порцией карточек (для HTMX). Vary: HX-Request
	не даёт браузеру показать из кэша порцию вместо страницы — например, по кнопке «Назад»."""

	def __init__(self, get_response):
		self.get_response = get_response

	def __call__(self, request):
		response = self.get_response(request)
		patch_vary_headers(response, ('HX-Request',))
		return response
