from django.db.models import Count
from django.utils.functional import SimpleLazyObject

from customUser.models import Profile
from post.media import ACCEPT, MAX_UPLOAD_MB
from post.models import ALT_MAX_LENGTH, MAX_IMAGES
from post.serializer import POST_MAX_LENGTH

THEMES = ('light', 'dark')


def _who_to_follow(request):
	profiles = Profile.objects.select_related('user').filter(user__is_active=True)
	if request.user.is_authenticated:
		me = request.user.profile
		profiles = profiles.exclude(pk=me.pk).exclude(pk__in=me.follows.values('pk'))
	return list(profiles.annotate(followers_count=Count('followed_by')).order_by('-followers_count', '-pk')[:3])


def ui(request):
	"""Общий контекст оболочки: тема из cookie и блок «Кого почитать».

	«Кого почитать» вычисляется лениво — запросы идут, только если шаблон его выводит.
	"""
	theme = request.COOKIES.get('theme', '')
	return {
		'theme': theme if theme in THEMES else '',
		'who_to_follow': SimpleLazyObject(lambda: _who_to_follow(request)),
		'post_max_length': POST_MAX_LENGTH,
		'image_accept': ACCEPT,
		'max_images': MAX_IMAGES,
		'max_upload_mb': MAX_UPLOAD_MB,
		'alt_max_length': ALT_MAX_LENGTH,
	}
