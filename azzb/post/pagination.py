"""Пагинация лент.

Хронологические ленты листаются курсором по (created_at, id): новые посты сверху не
сдвигают страницы, и не бывает дублей при «Показать ещё». «Горячее» сортируется по
лайкам, поэтому там обычные номера страниц.
"""
import base64
import binascii
import uuid
from datetime import datetime

from django.db.models import Q

PAGE_SIZE = 20
# Порция карточек для «Показать ещё» и бесконечной прокрутки.
PAGE_TEMPLATE = "azzb/includes/post_page.html"


def is_load_more(request):
	return request.headers.get("X-Requested-With") == "azzb-load-more"


def page_url(request, **params):
	"""Текущий адрес с заменёнными параметрами (например, ?tab=likes&cursor=…)."""
	query = request.GET.copy()
	for key, value in params.items():
		query[key] = value
	return f"{request.path}?{query.urlencode()}"


def encode_cursor(post):
	raw = f"{post.created_at.isoformat()}|{post.pk.hex}"
	return base64.urlsafe_b64encode(raw.encode()).decode().rstrip('=')


def decode_cursor(cursor):
	"""(created_at, id) из курсора или None, если курсора нет или он испорчен."""
	if not cursor:
		return None
	try:
		raw = base64.urlsafe_b64decode(cursor + '=' * (-len(cursor) % 4)).decode()
		created, pk = raw.split('|')
		return datetime.fromisoformat(created), uuid.UUID(pk)
	except (binascii.Error, UnicodeDecodeError, ValueError):
		return None


def cursor_page(queryset, cursor, size=PAGE_SIZE):
	"""Страница постов от новых к старым после курсора. Возвращает (посты, курсор следующей)."""
	queryset = queryset.order_by('-created_at', '-id')
	after = decode_cursor(cursor)
	if after:
		created, pk = after
		queryset = queryset.filter(Q(created_at__lt=created) | Q(created_at=created, id__lt=pk))
	items = list(queryset[:size + 1])
	if len(items) > size:
		items = items[:size]
		return items, encode_cursor(items[-1])
	return items, None


def number_page(queryset, page, size=PAGE_SIZE):
	"""Страница по номеру (с 1). Возвращает (посты, номер следующей или None)."""
	try:
		page = max(1, int(page))
	except (TypeError, ValueError):
		page = 1
	start = (page - 1) * size
	items = list(queryset[start:start + size + 1])
	if len(items) > size:
		return items[:size], page + 1
	return items, None
