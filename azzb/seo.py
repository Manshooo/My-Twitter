"""Микроразметка schema.org (JSON-LD) для поисковиков: пост, профиль, сайт.

Что индексировать, решает Profile.indexable; здесь — только содержимое разметки.
"""
import json

from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

# Как django.utils.html.json_script: «</script>» внутри текста поста не закроет тег.
_ESCAPES = {ord('<'): '\\u003C', ord('>'): '\\u003E', ord('&'): '\\u0026'}


def script(data):
	text = json.dumps({'@context': 'https://schema.org', **data}, ensure_ascii=False, separators=(',', ':'))
	return format_html('<script type="application/ld+json">{}</script>', mark_safe(text.translate(_ESCAPES)))


def _counter(action, count):
	return {'@type': 'InteractionCounter', 'interactionType': f'https://schema.org/{action}', 'userInteractionCount': count}


def person(request, profile):
	url = request.build_absolute_uri(reverse('profile', kwargs={'slug': profile.user.username}))
	data = {
		'@type': 'Person',
		'@id': url,
		'url': url,
		'name': profile.username,
		'alternateName': f'@{profile.user.username}',
		'identifier': str(profile.user_id),
	}
	if profile.has_custom_avatar:
		data['image'] = request.build_absolute_uri(profile.avatar.url)
	return data


def post(request, post):
	url = request.build_absolute_uri(reverse('post', args=[post.pk]))
	data = {
		'@type': 'SocialMediaPosting',
		'@id': url,
		'url': url,
		'datePublished': post.created_at.isoformat(),
		'author': person(request, post.author),
		'commentCount': post.replies_count,
		'interactionStatistic': [
			_counter('LikeAction', getattr(post, 'likes_n', 0)),
			_counter('ShareAction', post.reposts_count),
		],
	}
	if post.text:
		data['text'] = post.text
	if post.edited_at:
		data['dateModified'] = post.edited_at.isoformat()
	images = [request.build_absolute_uri(image.file.url) for image in post.images.all() if image.file]
	if images:
		data['image'] = images
	if post.quote_of_id and getattr(post, 'quote_available', False):
		data['sharedContent'] = {'@id': request.build_absolute_uri(reverse('post', args=[post.quote_of_id]))}
	return data


def profile_page(request, profile):
	data = {
		'@type': 'ProfilePage',
		'dateCreated': profile.user.date_joined.isoformat(),
		'mainEntity': person(request, profile),
	}
	if profile.bio:
		data['mainEntity']['description'] = profile.bio
	return data


def website(request):
	return {
		'@type': 'WebSite',
		'name': 'AzzB',
		'alternateName': 'AzzB.ru',
		'url': request.build_absolute_uri('/'),
	}
