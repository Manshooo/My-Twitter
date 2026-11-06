"""Сроки хранения удалённого (149-ФЗ «Об информации», ст. 10.1, п. 3).

Организатор распространения информации хранит на территории РФ сами сообщения пользователей
(тексты, картинки) до шести месяцев, а сведения о фактах их приёма и передачи и о пользователях —
год, и выдаёт их по законному запросу госорганов. Поэтому удаление на сайте мягкое: пост или
аккаунт сразу пропадают для всех, а стираются через RETENTION_CONTENT — командой purge_expired
(cron раз в сутки, см. docs/deploy/retention.md). Раньше срока по просьбе человека (152-ФЗ)
данные стирает модератор через админку. Журнал действий (ActivityRecord) живёт год.
"""
from datetime import timedelta

from django.utils import timezone

RETENTION_CONTENT = timedelta(days=183)
RETENTION_METADATA = timedelta(days=365)


def purge_expired(now=None):
	"""Стереть всё, у чего вышел срок хранения. Возвращает {что: сколько}."""
	from customUser.account import erase_account
	from customUser.models import CustomUser
	from post.models import Post
	from post.services import purge_posts

	from .models import ActivityRecord

	now = now or timezone.now()
	content_edge = now - RETENTION_CONTENT
	accounts = 0
	for user in CustomUser.objects.filter(deleted_at__lt=content_edge, erased_at__isnull=True):
		erase_account(user)
		accounts += 1
	posts = purge_posts(Post.objects.filter(deleted_at__lt=content_edge))
	records, _ = ActivityRecord.objects.filter(created_at__lt=now - RETENTION_METADATA).delete()
	return {'accounts': accounts, 'posts': posts, 'activity': records}
