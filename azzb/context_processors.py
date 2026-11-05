from django.db.models import Count
from django.utils.functional import SimpleLazyObject

from customUser.models import Profile, Theme
from post.media import ACCEPT, MAX_UPLOAD_MB
from post.models import ALT_MAX_LENGTH, MAX_IMAGES
from post.serializer import POST_MAX_LENGTH

THEMES = (Theme.LIGHT, Theme.DARK)


def current_theme(request):
	"""Тема страницы: выбор из аккаунта, иначе из cookie (гости и те, кто ещё не выбирал). '' — как в системе."""
	user = getattr(request, 'user', None)
	if user is not None and user.is_authenticated and user.theme:
		return user.theme
	theme = request.COOKIES.get('theme', '')
	return theme if theme in THEMES else ''


def _who_to_follow(request):
	profiles = Profile.objects.select_related('user').filter(user__is_active=True)
	if request.user.is_authenticated:
		me = request.user.profile
		profiles = profiles.exclude(pk=me.pk).exclude(pk__in=me.follows.values('pk'))
	return list(profiles.annotate(followers_count=Count('followed_by')).order_by('-followers_count', '-pk')[:3])


def ui(request):
	"""Общий контекст оболочки: тема и блок «Кого почитать».

	«Кого почитать» вычисляется лениво — запросы идут, только если шаблон его выводит.
	"""
	return {
		'theme': current_theme(request),
		'who_to_follow': SimpleLazyObject(lambda: _who_to_follow(request)),
		'post_max_length': POST_MAX_LENGTH,
		'image_accept': ACCEPT,
		'max_images': MAX_IMAGES,
		'max_upload_mb': MAX_UPLOAD_MB,
		'alt_max_length': ALT_MAX_LENGTH,
	}
