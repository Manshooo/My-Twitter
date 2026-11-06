from django.apps import AppConfig


class azzbConfig(AppConfig):
	default_auto_field = 'django.db.models.BigAutoField'
	name = 'azzb'

	def ready(self):
		from . import activity  # noqa: F401 — подключает сигналы входа и регистрации
