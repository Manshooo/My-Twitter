"""Уведомления (D1)."""
from django.db import models
from django.db.models import Q

from accounts.models import Profile
from post.models import Post


class Notification(models.Model):
	"""Одно событие для одного получателя. Создаётся и снимается только через notifications.services."""

	class Verb(models.TextChoices):
		LIKE = 'like', 'Лайк'
		REPLY = 'reply', 'Ответ'
		FOLLOW = 'follow', 'Подписка'
		REPOST = 'repost', 'Репост'
		QUOTE = 'quote', 'Цитата'
		MENTION = 'mention', 'Упоминание'
		FOLLOW_REQUEST = 'follow_req', 'Заявка на подписку'
		FOLLOW_ACCEPTED = 'follow_ok', 'Заявка одобрена'

	recipient = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='notifications', verbose_name='Кому')
	actor = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='+', verbose_name='Кто')
	verb = models.CharField('Что', max_length=10, choices=Verb.choices)
	# Лайк и репост — исходный пост, ответ, цитата и упоминание — сам новый пост, подписка — пусто.
	post = models.ForeignKey(Post, on_delete=models.CASCADE, null=True, blank=True, related_name='+', verbose_name='Пост')
	created_at = models.DateTimeField('Когда', auto_now_add=True)
	read_at = models.DateTimeField('Прочитано', null=True, blank=True)

	class Meta:
		verbose_name = 'Уведомление'
		verbose_name_plural = 'Уведомления'
		constraints = [
			# Двойной клик по лайку или подписке не плодит дублей. nulls_distinct — ради подписок
			# (post пустой); требует PostgreSQL 15+.
			models.UniqueConstraint(
				fields=['recipient', 'actor', 'verb', 'post'], nulls_distinct=False, name='notification_once',
			),
		]
		indexes = [
			models.Index(fields=['recipient', '-created_at'], name='notification_recent'),
			models.Index(fields=['recipient'], condition=Q(read_at__isnull=True), name='notification_unread'),
		]

	def __str__(self):
		return f'{self.actor} → {self.recipient}: {self.get_verb_display()}'
