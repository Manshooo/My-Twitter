from django.apps import AppConfig


class DmConfig(AppConfig):
	default_auto_field = 'django.db.models.BigAutoField'
	name = 'dm'
	verbose_name = 'Личные сообщения'

	def ready(self):
		import dm.signals  # noqa: F401
