"""Сроки хранения удалённого.

Законодательство страны, где работает сайт, может требовать хранить сообщения пользователей и
сведения о них какое-то время после удаления и выдавать их по законному запросу госорганов.
Поэтому удаление на сайте мягкое: пост, личное сообщение или аккаунт сразу пропадают для всех, а сообщения (тексты,
картинки) стираются через RETENTION_CONTENT, журнал действий (ActivityRecord) — через
RETENTION_METADATA, командой purge_expired (cron раз в сутки, см. docs/deploy/retention.md).
Раньше срока по просьбе человека данные стирает модератор через админку. Сроки — здесь, в одном месте.
"""
from datetime import timedelta

from django.utils import timezone

RETENTION_CONTENT = timedelta(days=183)
RETENTION_METADATA = timedelta(days=365)


def purge_expired(now=None):
	"""Стереть всё, у чего вышел срок хранения. Возвращает {что: сколько}."""
	from accounts.account import erase_account
	from accounts.models import CustomUser
	from dm.models import Message
	from dm.services import purge_messages
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
	messages = purge_messages(Message.objects.filter(deleted_at__lt=content_edge))
	records, _ = ActivityRecord.objects.filter(created_at__lt=now - RETENTION_METADATA).delete()
	return {'accounts': accounts, 'posts': posts, 'messages': messages, 'activity': records}
