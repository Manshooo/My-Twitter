from django.conf import settings
from django.db import models


class RateCounter(models.Model):
	"""Счётчик запросов в окне времени для лимитов частоты (azzb/ratelimit.py).

	Увеличивается одним атомарным INSERT … ON CONFLICT, поэтому верно считает при любом
	числе воркеров. Просроченные строки периодически удаляются там же.
	"""
	key = models.CharField(max_length=200)
	window = models.BigIntegerField('Номер окна')
	hits = models.PositiveIntegerField(default=0)
	expires_at = models.DateTimeField(db_index=True)

	class Meta:
		verbose_name = 'Счётчик лимита'
		verbose_name_plural = 'Счётчики лимитов'
		constraints = [models.UniqueConstraint(fields=['key', 'window'], name='rate_counter_key_window')]

	def __str__(self):
		return f'{self.key} #{self.window}: {self.hits}'


class ActivityRecord(models.Model):
	"""Журнал действий пользователей: кто, когда и с какого адреса входил (и неудачно пытался),
	менял пароль и почту, публиковал, правил и удалял. Входы — ещё и для писем о новом устройстве
	(accounts/devices.py). Нужен, чтобы отвечать на законные запросы госорганов: сведения о фактах приёма
	и передачи сообщений и о пользователях хранятся год (RETENTION_METADATA в azzb/retention.py)
	и выдаются только по такому запросу. Логин и почта копируются в запись:
	они должны пережить стирание аккаунта. Пишется через azzb.activity.record."""

	class Action(models.TextChoices):
		SIGNUP = 'signup', 'Регистрация'
		LOGIN = 'login', 'Вход'
		LOGIN_FAILED = 'login_failed', 'Неудачный вход'
		PASSWORD_CHANGE = 'password_change', 'Смена пароля'
		PASSWORD_RESET = 'password_reset', 'Сброс пароля'
		EMAIL_CHANGE = 'email_change', 'Смена почты'
		SESSIONS_END = 'sessions_end', 'Завершение сеансов'
		POST_CREATE = 'post_create', 'Пост или ответ'
		POST_EDIT = 'post_edit', 'Правка поста'
		POST_DELETE = 'post_delete', 'Удаление поста'
		ACCOUNT_DELETE = 'account_delete', 'Удаление аккаунта'

	created_at = models.DateTimeField('Когда', auto_now_add=True, db_index=True)
	action = models.CharField('Действие', max_length=20, choices=Action.choices)
	user = models.ForeignKey(
		settings.AUTH_USER_MODEL, verbose_name='Пользователь', null=True, blank=True,
		on_delete=models.SET_NULL, related_name='activity',
	)
	username = models.CharField('Логин на момент действия', max_length=150)
	email = models.CharField('Почта на момент действия', max_length=254, blank=True, default='')
	# Без внешнего ключа: запись должна жить и после того, как пост сотрут.
	post_id = models.UUIDField('Пост', null=True, blank=True)
	ip = models.GenericIPAddressField('IP-адрес', null=True, blank=True)
	user_agent = models.CharField('Браузер', max_length=400, blank=True, default='')

	class Meta:
		ordering = ['-created_at']
		verbose_name = 'Действие пользователя'
		verbose_name_plural = 'Журнал действий'
		indexes = [models.Index(fields=['user', '-created_at'], name='activity_user_recent')]

	def __str__(self):
		return f'{self.created_at:%d.%m.%Y %H:%M} @{self.username}: {self.get_action_display()}'
