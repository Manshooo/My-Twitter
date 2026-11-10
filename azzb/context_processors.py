from django.conf import settings
from django.utils.functional import SimpleLazyObject

from accounts.models import Theme
from moderation.models import Report
from moderation.services import can_moderate
from notifications.services import unread_count
from post.media import ACCEPT, MAX_UPLOAD_MB
from post.models import ALT_MAX_LENGTH, MAX_IMAGES
from post.serializer import POST_MAX_LENGTH

from .discover import trends, who_to_follow

THEMES = (Theme.LIGHT, Theme.DARK)


def current_theme(request):
	"""Тема страницы: выбор из аккаунта, иначе из cookie (гости и те, кто ещё не выбирал). '' — как в системе."""
	user = getattr(request, 'user', None)
	if user is not None and user.is_authenticated and user.theme:
		return user.theme
	theme = request.COOKIES.get('theme', '')
	return theme if theme in THEMES else ''


def ui(request):
	"""Общий контекст оболочки: тема, «Кого почитать» и тренды.

	«Кого почитать» и тренды вычисляются лениво — запросы идут, только если шаблон их выводит.
	"""
	return {
		'theme': current_theme(request),
		'who_to_follow': SimpleLazyObject(lambda: who_to_follow(request.user)),
		'trends': SimpleLazyObject(trends),
		'post_max_length': POST_MAX_LENGTH,
		'image_accept': ACCEPT,
		'max_images': MAX_IMAGES,
		'max_upload_mb': MAX_UPLOAD_MB,
		'alt_max_length': ALT_MAX_LENGTH,
		'support_email': settings.SUPPORT_EMAIL,
		'legal_operator': settings.LEGAL_OPERATOR,
		# Пункт «Модерация» в меню и число открытых жалоб на нём (E4).
		'can_moderate': SimpleLazyObject(lambda: can_moderate(request.user)),
		'open_reports': SimpleLazyObject(lambda: Report.objects.filter(status=Report.Status.OPEN).count()),
		'unread_notifications': SimpleLazyObject(
			lambda: unread_count(request.user) if request.user.is_authenticated else 0,
		),
	}
