"""Лимиты частоты (E2): посты, лайки, подписки, жалобы.

Вход, регистрацию, сброс пароля и письма подтверждения ограничивает сам allauth
(ACCOUNT_RATE_LIMITS в settings.py, счётчики в кэше). Наши счётчики — таблица RateCounter
в PostgreSQL с атомарным увеличением, поэтому они верны при любом числе воркеров gunicorn.
"""
import random
import re
import time
from datetime import datetime, timedelta, timezone
from functools import wraps

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render

from .htmx import is_htmx
from .models import RateCounter

UNITS = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
RATE_RE = re.compile(r'^(\d+)/(\d*)([smhd])$')
# Доля запросов, которые заодно чистят просроченные счётчики.
CLEANUP_CHANCE = 0.01


def _now():
	"""Отдельной функцией — чтобы тесты могли остановить часы."""
	return time.time()


def parse_rate(rate):
	"""'8/m' → (8, 60); '5/15m' → (5, 900)."""
	match = RATE_RE.match(rate)
	if not match:
		raise ValueError(f'Неверный лимит: {rate!r}')
	count, multiplier, unit = match.groups()
	return int(count), int(multiplier or 1) * UNITS[unit]


def client_ip(request):
	"""IP посетителя. За nginx в REMOTE_ADDR всегда 127.0.0.1 (или пусто при unix-сокете),
	поэтому настоящий адрес берём из заголовка, который nginx ставит сам (CLIENT_IP_HEADER,
	по умолчанию на проде X-Real-IP; см. docs/deploy/security.md). Нет заголовка — REMOTE_ADDR."""
	header = getattr(settings, 'CLIENT_IP_HEADER', '')
	if header:
		ip = request.headers.get(header, '').split(',')[0].strip()
		if ip:
			return ip
	return request.META.get('REMOTE_ADDR') or '0.0.0.0'


def user_or_ip(request):
	"""Ключ счётчика: пользователь, а для гостей — IP."""
	if request.user.is_authenticated:
		return f'u{request.user.pk}'
	return f'ip{client_ip(request)}'


def hit(key, rate):
	"""Засчитать запрос. True — лимит превышен (этот запрос уже лишний)."""
	limit, period = parse_rate(rate)
	now = _now()
	window = int(now // period)
	expires_at = datetime.fromtimestamp((window + 1) * period, tz=timezone.utc)
	table = RateCounter._meta.db_table
	with connection.cursor() as cursor:
		cursor.execute(
			f'INSERT INTO {table} (key, "window", hits, expires_at) VALUES (%s, %s, 1, %s) '
			f'ON CONFLICT (key, "window") DO UPDATE SET hits = {table}.hits + 1 RETURNING hits',
			[f'{key}:{limit}/{period}', window, expires_at],
		)
		hits = cursor.fetchone()[0]
	if random.random() < CLEANUP_CHANCE:
		RateCounter.objects.filter(expires_at__lt=datetime.now(timezone.utc) - timedelta(minutes=1)).delete()
	return hits > limit


def is_limited(request, group, *rates):
	"""Засчитать запрос во всех окнах (и минутном, и часовом) и сказать, превышено ли хоть одно."""
	if not getattr(settings, 'RATELIMIT_ENABLE', True):
		return False
	key = f'{group}:{user_or_ip(request)}'
	return any([hit(key, rate) for rate in rates])


def limited_response(request, message):
	"""429: для htmx и API {"errors": [...]} (azzb.js покажет текст тостом или в composer),
	для обычной формы — страница 429.html."""
	if is_htmx(request) or request.path.startswith('/api/'):
		response = JsonResponse({'errors': [message]}, status=429)
	else:
		response = render(request, '429.html', {'message': message}, status=429)
	response['Retry-After'] = '60'
	return response


def rate_limit(group, *rates, message='Слишком часто. Подождите немного и попробуйте снова.'):
	"""Ограничивает POST-запросы к просмотру: например, rate_limit('post', '8/m', '60/h').

	Группа общая для страниц и API — пост через composer и через /api/new-post/ считаются вместе.
	"""
	for rate in rates:
		parse_rate(rate)  # ошибка в записи лимита — сразу при импорте, а не на первом запросе

	def decorator(view):
		@wraps(view)
		def wrapper(request, *args, **kwargs):
			if request.method == 'POST' and is_limited(request, group, *rates):
				return limited_response(request, message)
			return view(request, *args, **kwargs)
		return wrapper
	return decorator
