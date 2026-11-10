"""«Кого читать» (D6) и тренды (D7)."""
from datetime import timedelta

from django.core.cache import cache
from django.db.models import Count, IntegerField, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone

from customUser.models import Block, FollowThrough, Mute, Profile
from post.models import Hashtag

TRENDS_WINDOW = timedelta(hours=24)
TRENDS_CACHE_SECONDS = 300
TRENDS_LIMIT = 10


def who_to_follow(user, limit=3):
	"""Друзья друзей — кого читают мои подписки, по числу таких связей (mutual), — затем
	популярные авторы. Без меня, моих подписок, заглушённых, блокировок в любую сторону,
	отключённых, удалённых и забаненных. Гостю — просто популярные."""
	profiles = (
		Profile.objects.select_related('user')
		.filter(user__is_active=True, user__deleted_at__isnull=True)
		.exclude(user__banned_until__gt=timezone.now())
		.annotate(followers_count=Count('followed_by', distinct=True))
	)
	if not user.is_authenticated:
		return list(profiles.order_by('-followers_count', '-pk')[:limit])
	me = user.profile
	my_follows = FollowThrough.objects.filter(follower=me).values('followee')
	mutual = (
		FollowThrough.objects.filter(followee=OuterRef('pk'), follower__in=my_follows)
		.order_by().values('followee').annotate(n=Count('*')).values('n')
	)
	return list(
		profiles.exclude(pk=me.pk).exclude(pk__in=my_follows)
		.exclude(pk__in=Block.objects.filter(blocker=me).values('blocked'))
		.exclude(pk__in=Block.objects.filter(blocked=me).values('blocker'))
		.exclude(pk__in=Mute.objects.filter(muter=me).values('muted'))
		.annotate(mutual=Coalesce(Subquery(mutual, output_field=IntegerField()), 0))
		.order_by('-mutual', '-followers_count', '-pk')[:limit]
	)


def compute_trends(now=None, limit=TRENDS_LIMIT):
	"""Теги за последние сутки: сначала по числу разных авторов (один человек тег не раскрутит),
	затем по числу постов. Учитываются только посты, видные всем: не удалённые, не скрытые,
	от активных незабаненных аккаунтов."""
	now = now or timezone.now()
	recent = Q(
		posts__created_at__gte=now - TRENDS_WINDOW, posts__deleted_at__isnull=True, posts__hidden_at__isnull=True,
		posts__author__user__is_active=True,
	) & ~Q(posts__author__user__banned_until__gt=now)
	return list(
		Hashtag.objects.annotate(
			authors=Count('posts__author', filter=recent, distinct=True),
			uses=Count('posts', filter=recent, distinct=True),
		)
		.filter(uses__gt=0)
		.order_by('-authors', '-uses', 'name')
		.values('name', 'authors', 'uses')[:limit]
	)


def trends(limit=5):
	"""Тренды из кэша: пересчёт не чаще раза в TRENDS_CACHE_SECONDS, а не на каждой странице."""
	return cache.get_or_set('azzb:trends', compute_trends, TRENDS_CACHE_SECONDS)[:limit]
