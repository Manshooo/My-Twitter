"""Запись поведенческих событий (docs/data-collection.md, разделы 5–6).

Только у вошедших и принявших текущую редакцию согласия (accounts.consent). О посте событие
принимается, только если человек этот пост видит (Post.objects.visible_to).
"""
import re
import uuid

from django.db.models import F
from django.utils import timezone

from accounts import consent
from post.models import Hashtag, Post

from . import partitions
from .models import Device, Impression, InteractionEvent, Surface

BATCH_MAX = 50
DWELL_MAX = 600
PHONE = re.compile(r'Mobi|Android|iPhone|iPod', re.I)

# Что браузер может прислать сам; open, not_interested, unlike, unfollow, search пишет сервер.
CLIENT_KINDS = {
	Impression.Kind.IMPRESSION, Impression.Kind.DWELL,
	InteractionEvent.Kind.EXPAND, InteractionEvent.Kind.MEDIA_OPEN, InteractionEvent.Kind.PROFILE_CLICK,
	InteractionEvent.Kind.TAG_CLICK, InteractionEvent.Kind.LINK_CLICK, InteractionEvent.Kind.SEARCH_CLICK,
}
SURFACES = set(Surface.values)


def collecting(user):
	return user.is_authenticated and consent.is_current(user)


def device_of(request):
	return Device.PHONE if PHONE.search(request.headers.get('User-Agent', '')) else Device.DESKTOP


def surface_from_referer(request):
	"""Откуда открыли пост: поверхность страницы, с которой пришли (по Referer своего сайта)."""
	from urllib.parse import urlsplit

	from django.urls import Resolver404, resolve

	from azzb.context_processors import SURFACES

	referer = urlsplit(request.headers.get('Referer', ''))
	if not referer.path or referer.netloc != request.get_host():
		return Surface.OTHER
	try:
		return SURFACES.get(resolve(referer.path).url_name, Surface.OTHER)
	except Resolver404:
		return Surface.OTHER


def count_views(user, post_ids, now):
	"""+1 к Post.views_count за каждый пост, который человек раньше не видел и не открывал.
	«Раньше» — пока хранятся показы (30–60 дней): отдельной таблицы «кто что видел навсегда» нет.
	Вызывается до записи новых событий. Свои посты автору не засчитываются."""
	post_ids = set(post_ids)
	if not post_ids:
		return 0
	seen = set(Impression.objects.filter(user=user, post_id__in=post_ids).values_list('post_id', flat=True))
	seen |= set(InteractionEvent.objects.filter(
		user=user, kind=InteractionEvent.Kind.OPEN, post_id__in=post_ids,
	).values_list('post_id', flat=True))
	new = post_ids - seen
	if not new:
		return 0
	return Post.objects.filter(pk__in=new).exclude(author_id=user.pk).update(views_count=F('views_count') + 1)


def record(request, kind, *, post=None, target=None, surface=Surface.OTHER, **data):
	"""Серверное событие (InteractionEvent.Kind) от имени request.user."""
	if not collecting(request.user):
		return
	now = timezone.now()
	partitions.ensure(now)
	if kind == InteractionEvent.Kind.OPEN and post is not None and count_views(request.user, [post.pk], now):
		# Страница ещё не отрисована: пусть открывший сразу увидит себя в счётчике.
		post.views_count += 1
	InteractionEvent.objects.create(
		created_at=now, user=request.user, kind=kind, surface=surface, device=device_of(request),
		post=post, target=target, data=data,
	)


def _int(value, low, high):
	try:
		value = int(value)
	except (TypeError, ValueError):
		return None
	return value if low <= value <= high else None


def _uuid(value):
	try:
		return uuid.UUID(str(value))
	except (TypeError, ValueError, AttributeError):
		return None


def _domain(value):
	value = str(value or '').lower().strip()[:253]
	return value if re.fullmatch(r'[a-z0-9.-]+\.[a-z]{2,}', value) else None


def ingest(request, items):
	"""Пачка событий из браузера. Неизвестное и чужое молча отбрасывается. Возвращает число записанных."""
	if not collecting(request.user) or not isinstance(items, list):
		return 0
	user = request.user
	items = [item for item in items[:BATCH_MAX] if isinstance(item, dict) and item.get('kind') in CLIENT_KINDS]
	post_ids = {pid for pid in (_uuid(item.get('post')) for item in items) if pid}
	visible = set(Post.objects.visible_to(user).filter(pk__in=post_ids).values_list('pk', flat=True))
	tags = {item.get('tag') for item in items if item.get('kind') == InteractionEvent.Kind.TAG_CLICK}
	known_tags = set(Hashtag.objects.filter(name__in=[t for t in tags if isinstance(t, str)]).values_list('name', flat=True))
	now = timezone.now()
	device = device_of(request)
	impressions, events, seen = [], [], set()
	for item in items:
		kind = item['kind']
		post = _uuid(item.get('post'))
		# Клик в поиске может вести не к посту, а к человеку или тегу — тогда поста нет.
		if post not in visible and not (kind == InteractionEvent.Kind.SEARCH_CLICK and post is None):
			continue
		surface = item.get('surface') if item.get('surface') in SURFACES else Surface.OTHER
		if kind in (Impression.Kind.IMPRESSION, Impression.Kind.DWELL):
			feed = _uuid(item.get('feed'))
			seconds = _int(item.get('seconds'), 1, DWELL_MAX) if kind == Impression.Kind.DWELL else None
			if kind == Impression.Kind.DWELL and seconds is None:
				continue
			key = (kind, post, feed)
			if key in seen:
				continue
			seen.add(key)
			impressions.append(Impression(
				created_at=now, user=user, post_id=post, kind=kind, surface=surface, feed=feed,
				position=_int(item.get('position'), 0, 10000), seconds=seconds, device=device,
			))
			continue
		data = {}
		if kind == InteractionEvent.Kind.TAG_CLICK:
			if item.get('tag') not in known_tags:
				continue
			data['tag'] = item['tag']
		elif kind == InteractionEvent.Kind.LINK_CLICK:
			if not _domain(item.get('domain')):
				continue
			data['domain'] = _domain(item['domain'])
		elif kind == InteractionEvent.Kind.MEDIA_OPEN:
			data['index'] = _int(item.get('index'), 0, 3) or 0
		elif kind == InteractionEvent.Kind.SEARCH_CLICK:
			data['position'] = _int(item.get('position'), 0, 10000)
			if item.get('result') in ('post', 'person', 'tag'):
				data['result'] = item['result']
		events.append(InteractionEvent(created_at=now, user=user, kind=kind, surface=surface, device=device, post_id=post, data=data))
	if impressions or events:
		partitions.ensure(now)
		count_views(user, [i.post_id for i in impressions if i.kind == Impression.Kind.IMPRESSION], now)
		Impression.objects.bulk_create(impressions)
		InteractionEvent.objects.bulk_create(events)
	return len(impressions) + len(events)


def erase_user_events(user):
	"""Стереть поведенческие данные человека (удаление аккаунта)."""
	from .models import NegativeFeedback

	Impression.objects.filter(user=user).delete()
	InteractionEvent.objects.filter(user=user).delete()
	NegativeFeedback.objects.filter(user=user).delete()


def purge(now=None):
	"""Удалить секции старше сроков хранения (partitions.RETENTION). Возвращает число секций."""
	now = now or timezone.now()
	partitions.ensure(now)
	return sum(partitions.drop_older(table, now - keep) for table, keep in partitions.RETENTION.items())
