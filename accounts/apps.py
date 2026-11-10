from django.apps import AppConfig


class AccountsConfig(AppConfig):
	"""Аккаунты и профили: пользователь, профиль, подписки, блокировки, настройки аккаунта.

	Пакет называется accounts, а метка приложения осталась прежней — customUser. По метке Django
	называет таблицы (customUser_customuser…), записывает историю миграций и ищет модель пользователя
	(AUTH_USER_MODEL = 'customUser.CustomUser'); на неё же ссылаются allauth и журнал админки.
	Смена метки на живой базе — переименование таблиц и правка чужих миграций без всякой пользы,
	поэтому в коде пишем accounts, а в базе остаётся customUser.
	"""

	default_auto_field = 'django.db.models.BigAutoField'
	name = 'accounts'
	label = 'customUser'
	verbose_name = 'Пользователи'

	def ready(self):
		# Импорт ради побочного эффекта: регистрирует обработчики сигналов (создание профиля).
		from . import signals  # noqa: F401
