"""Поиск (D3): посты — полнотекстовый по-русски, люди — по логину и имени с опечатками, теги — по началу."""
from django.contrib.postgres.search import SearchQuery, SearchRank, TrigramSimilarity
from django.db.models import Count, F, Q
from django.db.models.functions import Greatest
from django.utils import timezone

from accounts.models import Block, Profile
from post.models import Hashtag, Post
from post.text import HASHTAG_MAX_LENGTH

QUERY_MAX_LENGTH = 100
PEOPLE_LIMIT = 30
TAGS_LIMIT = 30


def clean_query(raw):
	return ' '.join((raw or '').split())[:QUERY_MAX_LENGTH]


def posts(user, query):
	"""Посты и ответы, которые человек видит, кроме заглушённых. Синтаксис как в поисковиках:
	"точная фраза", -исключить, or. Сначала самые подходящие, при равенстве — свежие."""
	search = SearchQuery(query, config='russian', search_type='websearch')
	return (
		Post.objects.for_feed(user).without_muted(user).filter(is_repost=False, search_vector=search)
		.annotate(rank=SearchRank(F('search_vector'), search))
		.order_by('-rank', '-created_at', '-id')
	)


def people(user, query):
	"""Люди из Profile.objects.public(), кроме забаненных, по логину или отображаемому имени: подстрока или похожее
	написание (pg_trgm). Без тех, с кем у пользователя блокировка в любую сторону."""
	query = query.lstrip('@')
	if not query:
		return Profile.objects.none()
	found = (
		Profile.objects.public().select_related('user')
		.exclude(user__banned_until__gt=timezone.now())
		.filter(
			Q(user__username__icontains=query) | Q(username__icontains=query)
			| Q(user__username__trigram_similar=query) | Q(username__trigram_similar=query)
		)
		.annotate(similarity=Greatest(
			TrigramSimilarity('user__username', query), TrigramSimilarity('username', query),
		))
	)
	if user.is_authenticated:
		me = user.profile
		found = found.exclude(pk__in=Block.objects.filter(blocker=me).values('blocked')).exclude(
			pk__in=Block.objects.filter(blocked=me).values('blocker'),
		)
	return found.order_by('-similarity', 'user__username')[:PEOPLE_LIMIT]


def tags(query):
	"""Теги, начинающиеся с запроса, самые популярные — первыми."""
	prefix = query.lstrip('#').lower()[:HASHTAG_MAX_LENGTH]
	if not prefix:
		return Hashtag.objects.none()
	return (
		Hashtag.objects.filter(name__startswith=prefix)
		.annotate(uses=Count('posts', filter=Q(posts__deleted_at__isnull=True)))
		.filter(uses__gt=0)
		.order_by('-uses', 'name')[:TAGS_LIMIT]
	)
