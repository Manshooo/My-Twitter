from django.core.exceptions import ValidationError
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from django.db.models import Exists, OuterRef, Q
from django.db.models.functions import Length

from accounts.models import USERNAME_MAX_LENGTH, Block, FollowThrough, Profile
from accounts.serializers import ProfileSerializer
from azzb.activity import Action, record
from azzb.ratelimit import rate_limit
from post.services import find_post_target, find_reply_target, publish_post
from post.views import ERROR_STATUS, POST_RATES, render_cards


def _getlist(data, key):
	"""Список значений и из multipart-формы (QueryDict), и из JSON."""
	if hasattr(data, 'getlist'):
		return data.getlist(key)
	value = data.get(key, [])
	return value if isinstance(value, list) else [value]


@rate_limit('post', *POST_RATES)
@api_view(['POST'])
def create_post(request):
	"""Новый пост или ответ: текст и до 4 картинок
	(multipart: text, images[], alt[] в том же порядке, reply_to — id поста, если это ответ,
	quote_of — если цитата)."""
	data = request.data
	text = data.get('text')
	try:
		post = publish_post(
			request.user.profile,
			text if isinstance(text, str) else '',
			request.FILES.getlist('images'),
			_getlist(data, 'alt'),
			reply_to=find_reply_target(request.user, data.get('reply_to')),
			quote_of=find_post_target(request.user, data.get('quote_of'), 'quote'),
		)
	except ValidationError as error:
		code = ERROR_STATUS.get(getattr(error, 'code', None), status.HTTP_400_BAD_REQUEST)
		return Response({'errors': error.messages}, status=code)
	record(request, Action.POST_CREATE, post=post)
	return render_cards(request, [post])


@api_view(['GET'])
def profiles_list(request):
	"""
	List profiles.
	"""
	nextPage = 1
	previousPage = 1
	profiles = Profile.objects.public().select_related('user').order_by('pk')
	page = request.GET.get('page', 1)
	paginator = Paginator(profiles, 10)
	try:
		data = paginator.page(page)
	except PageNotAnInteger:
		data = paginator.page(1)
	except EmptyPage:
		data = paginator.page(paginator.num_pages)
	serializer = ProfileSerializer(data, context={'request': request}, many=True)
	if data.has_next():
		nextPage = data.next_page_number()
	if data.has_previous():
		previousPage = data.previous_page_number()
	return Response({'data': serializer.data , 'count': paginator.count, 'numpages' : paginator.num_pages, 'nextlink': '/api/profiles/?page=' + str(nextPage), 'prevlink': '/api/profiles/?page=' + str(previousPage)})

@api_view(['GET', 'PUT', 'PATCH'])
def profile_details(request, pk):
	"""
	Retrieve profile by id/pk; update — only your own.
	"""
	# DELETE убран: удаление профиля без пользователя ломало сайт для этого аккаунта
	# (везде используется request.user.profile). Удаление аккаунта — отдельная задача (E6).
	try:
		profile = Profile.objects.public().select_related('user').get(pk=pk)
	except Profile.DoesNotExist:
		return Response(status=status.HTTP_404_NOT_FOUND)

	if request.method == 'GET':
		serializer = ProfileSerializer(profile, context={'request': request})
		return Response(serializer.data)

	if profile.user_id != request.user.id:
		return Response(status=status.HTTP_403_FORBIDDEN)

	serializer = ProfileSerializer(
		profile,
		data=request.data,
		partial=request.method == 'PATCH',
		context={'request': request},
	)
	if serializer.is_valid():
		serializer.save()
		return Response(serializer.data)
	return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ---------- @упоминания: подсказки в composer и проверка ссылок (D2) ----------

MENTION_SUGGESTIONS = 8
EXISTS_MAX_NAMES = 50


def _mentionable():
	"""Кого можно упомянуть — тех же, кого сайт показывает другим (Profile.objects.public())."""
	return Profile.objects.public().select_related('user')


@rate_limit('mention', '120/m', '2000/h')
@api_view(['GET'])
def mention_suggestions(request):
	"""Подсказки для @ в composer: логин начинается с q или имя содержит q. Сначала те,
	на кого я подписан. Без меня и без тех, с кем блокировка в любую сторону."""
	query = (request.query_params.get('q') or '').lstrip('@').strip()[:USERNAME_MAX_LENGTH]
	if not query:
		return Response({'results': []})
	me = request.user.profile
	people = (
		_mentionable()
		.filter(Q(user__username__istartswith=query) | Q(username__icontains=query))
		.exclude(pk=me.pk)
		.exclude(pk__in=Block.objects.filter(blocker=me).values('blocked'))
		.exclude(pk__in=Block.objects.filter(blocked=me).values('blocker'))
		.annotate(followed=Exists(FollowThrough.objects.filter(follower=me, followee=OuterRef('pk'))))
		.order_by('-followed', Length('user__username'), 'user__username')[:MENTION_SUGGESTIONS]
	)
	return Response({'results': [{
		'username': person.user.username,
		'name': person.username,
		'avatar': person.avatar.url if person.has_custom_avatar else None,
		'initial': person.initial,
		'tone': person.avatar_tone,
		'verified': person.is_verified,
	} for person in people]})


@rate_limit('mention', '120/m', '2000/h')
@api_view(['GET'])
def existing_users(request):
	"""Какие из логинов (?names=a,b) существуют. По ответу azzb.js превращает ссылки
	на несуществующие @логины в обычный текст: в ленте их ставят по виду, без запроса к базе."""
	names = [name for name in (request.query_params.get('names') or '').split(',') if name][:EXISTS_MAX_NAMES]
	found = _mentionable().filter(user__username__in=names).values_list('user__username', flat=True)
	return Response({'existing': sorted(found)})
