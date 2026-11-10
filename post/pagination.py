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
	"""«Показать ещё» и бесконечная прокрутка ходят через htmx: ему нужна только порция карточек."""
	return request.headers.get("HX-Request") == "true"


def page_url(request, **params):
	"""Текущий адрес с заменёнными параметрами (например, ?tab=likes&cursor=…)."""
	query = request.GET.copy()
	for key, value in params.items():
		query[key] = value
	return f"{request.path}?{query.urlencode()}"


def encode_cursor(post, field='created_at'):
	raw = f"{getattr(post, field).isoformat()}|{post.pk.hex}"
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


def cursor_page(queryset, cursor, size=PAGE_SIZE, ascending=False, field='created_at'):
	"""Страница постов после курсора: от новых к старым, а для ветки ответов (ascending) —
	от старых к новым. field — время, по которому листаем (закладки — по времени закладки).
	Возвращает (посты, курсор следующей)."""
	if ascending:
		queryset = queryset.order_by(field, 'id')
	else:
		queryset = queryset.order_by(f'-{field}', '-id')
	after = decode_cursor(cursor)
	if after:
		moment, pk = after
		op = 'gt' if ascending else 'lt'
		queryset = queryset.filter(Q(**{f'{field}__{op}': moment}) | Q(**{field: moment, f'id__{op}': pk}))
	items = list(queryset[:size + 1])
	if len(items) > size:
		items = items[:size]
		return items, encode_cursor(items[-1], field)
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
