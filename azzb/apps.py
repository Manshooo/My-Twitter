from django.apps import AppConfig


class AzzbConfig(AppConfig):
	default_auto_field = 'django.db.models.BigAutoField'
	name = 'azzb'
	verbose_name = 'Сайт'

	def ready(self):
		from . import activity  # noqa: F401 — подключает сигналы входа и регистрации
