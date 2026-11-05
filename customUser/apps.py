from django.apps import AppConfig


class CustomUserConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'customUser'

    def ready(self):
        import customUser.signals