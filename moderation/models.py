"""Жалобы и баны (E4)."""
from django.conf import settings
from django.db import models
from django.db.models import Q

from customUser.models import Profile
from post.models import Post


class Reason(models.TextChoices):
	SPAM = 'spam', 'Спам или реклама'
	ABUSE = 'abuse', 'Оскорбления или травля'
	HATE = 'hate', 'Разжигание ненависти'
	VIOLENCE = 'violence', 'Угрозы или призывы к насилию'
	ADULT = 'adult', 'Откровенный или шокирующий контент'
	ILLEGAL = 'illegal', 'Нарушает закон'
	IMPERSONATION = 'impersonation', 'Выдаёт себя за другого'
	OTHER = 'other', 'Другое'


class Report(models.Model):
	"""Жалоба на пост или на профиль. У жалобы на пост profile — его автор: так в очереди
	видно, сколько жалоб на человека в целом, и бан выдаётся из той же карточки."""

	class Status(models.TextChoices):
		OPEN = 'open', 'Новая'
		RESOLVED = 'resolved', 'Приняты меры'
		DISMISSED = 'dismissed', 'Отклонена'

	reporter = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='reports_made', verbose_name='Кто пожаловался')
	post = models.ForeignKey(Post, on_delete=models.CASCADE, null=True, blank=True, related_name='reports', verbose_name='Пост')
	profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='reports_received', verbose_name='На кого')
	reason = models.CharField('Причина', max_length=20, choices=Reason.choices)
	comment = models.CharField('Комментарий', max_length=500, blank=True, default='')
	status = models.CharField('Статус', max_length=10, choices=Status.choices, default=Status.OPEN, db_index=True)
	created_at = models.DateTimeField('Когда', auto_now_add=True)
	resolved_at = models.DateTimeField('Когда рассмотрена', null=True, blank=True)
	resolved_by = models.ForeignKey(
		settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+', verbose_name='Модератор',
	)
	resolution = models.CharField('Решение', max_length=200, blank=True, default='')

	class Meta:
		ordering = ['-created_at']
		verbose_name = 'Жалоба'
		verbose_name_plural = 'Жалобы'
		permissions = [('moderate', 'Может разбирать жалобы, скрывать посты и банить')]
		constraints = [
			# Одна открытая жалоба от человека на один пост (или профиль): повторная её обновляет.
			models.UniqueConstraint(
				fields=['reporter', 'post', 'profile'], condition=Q(status='open'),
				nulls_distinct=False, name='one_open_report',
			),
		]

	def __str__(self):
		target = f'пост {self.post_id}' if self.post_id else f'@{self.profile}'
		return f'{self.get_reason_display()}: {target}'


class Ban(models.Model):
	"""История банов. Текущий бан продублирован в CustomUser.banned_until — его проверяют
	middleware и Post.objects.visible_to без лишних запросов."""
	user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bans', verbose_name='Пользователь')
	reason = models.CharField('Причина', max_length=500)
	until = models.DateTimeField('До', null=True, blank=True, help_text='Пусто — навсегда')
	created_by = models.ForeignKey(
		settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+', verbose_name='Модератор',
	)
	created_at = models.DateTimeField('Когда', auto_now_add=True)
	lifted_at = models.DateTimeField('Снят досрочно', null=True, blank=True)
	lifted_by = models.ForeignKey(
		settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+', verbose_name='Кто снял',
	)

	class Meta:
		ordering = ['-created_at']
		verbose_name = 'Бан'
		verbose_name_plural = 'Баны'

	def __str__(self):
		return f'{self.user} до {self.until or "навсегда"}'
