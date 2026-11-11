"""ASGI: WebSocket /ws/ (F1). На проде этот процесс (uvicorn, сервис ws в docker-compose.prod.yml)
получает от nginx только /ws/; страницы отдаёт gunicorn (azzb.wsgi). При разработке uvicorn
отдаёт и то и другое — docs/deploy/realtime.md."""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'azzb.settings')
# До импорта consumers: им нужны загруженные приложения Django.
django_application = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402
from django.urls import path  # noqa: E402

from .consumers import UserConsumer  # noqa: E402

application = ProtocolTypeRouter({
	'http': django_application,
	# Origin из ALLOWED_HOSTS: чужая страница не откроет сокет с cookie нашего пользователя.
	'websocket': AllowedHostsOriginValidator(AuthMiddlewareStack(URLRouter([
		path('ws/', UserConsumer.as_asgi()),
	]))),
})
