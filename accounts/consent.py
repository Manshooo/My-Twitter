"""Редакция документов и согласие на обработку ПДн (C5, E6, docs/data-collection.md, раздел 10)."""
from datetime import date

from django.utils import timezone

# Дата текущей редакции правил, политики и согласия. Меняете текст — меняйте и дату: все, кто
# согласился раньше, увидят экран новой редакции (accounts/middleware.ConsentMiddleware).
EDITION = date(2026, 11, 12)


def is_current(user):
	"""Принял ли человек текущую редакцию согласия. Пока нет — поведенческие события не пишутся."""
	at = getattr(user, 'pd_consent_at', None)
	return at is not None and timezone.localtime(at).date() >= EDITION
