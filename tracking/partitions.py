"""Месячные секции таблиц событий: создать наперёд, удалить старые.

Секция на месяц — `<таблица>_yYYYYmMM`. Секции по умолчанию нет: строка за месяц без секции
не запишется, поэтому `ensure` вызывается и перед записью, и в purge_expired. Без кэша в процессе:
секция, созданная в откатившейся транзакции, пропадает вместе с ней.
"""
from datetime import date, datetime, timedelta, timezone as dt_timezone

from django.db import connection

TABLES = ('tracking_impression', 'tracking_interactionevent')


def _month(day):
	return date(day.year, day.month, 1)


def _next(month):
	return date(month.year + month.month // 12, month.month % 12 + 1, 1)


def _name(table, month):
	return f'{table}_y{month.year}m{month.month:02d}'


def _bound(month):
	return datetime(month.year, month.month, 1, tzinfo=dt_timezone.utc).isoformat()


def ensure(now, ahead=1):
	"""Секции текущего месяца и `ahead` следующих. Обычно — один SELECT: всё уже есть."""
	months = [_month(now.astimezone(dt_timezone.utc))]
	for _ in range(ahead):
		months.append(_next(months[-1]))
	wanted = [(table, month) for month in months for table in TABLES]
	with connection.cursor() as cursor:
		cursor.execute('SELECT ' + ', '.join(['to_regclass(%s) IS NULL'] * len(wanted)), [_name(t, m) for t, m in wanted])
		missing = [item for item, absent in zip(wanted, cursor.fetchone()) if absent]
		for table, month in missing:
			cursor.execute(
				f'CREATE TABLE IF NOT EXISTS {_name(table, month)} PARTITION OF {table} '
				f"FOR VALUES FROM ('{_bound(month)}') TO ('{_bound(_next(month))}')"
			)


def drop_older(table, edge):
	"""Удалить секции, целиком лежащие раньше `edge`. Возвращает их число."""
	with connection.cursor() as cursor:
		cursor.execute(
			'SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid '
			'JOIN pg_class p ON p.oid = i.inhparent WHERE p.relname = %s', [table],
		)
		names = [row[0] for row in cursor.fetchall()]
		dropped = 0
		for name in names:
			year, month = int(name[-7:-3]), int(name[-2:])
			end = _next(date(year, month, 1))
			if datetime(end.year, end.month, 1, tzinfo=dt_timezone.utc) <= edge:
				cursor.execute(f'DROP TABLE {name}')
				dropped += 1
	return dropped


RETENTION = {
	'tracking_impression': timedelta(days=30),
	'tracking_interactionevent': timedelta(days=180),
}
