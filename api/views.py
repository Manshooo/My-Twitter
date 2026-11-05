import uuid

from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.shortcuts import render
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from django.core.exceptions import ValidationError

from customUser.serializers import ProfileSerializer
from customUser.models import Profile
from post.models import Post
from post.pagination import PAGE_TEMPLATE
from post.services import publish_post

def _getlist(data, key):
	"""Список значений и из multipart-формы (QueryDict), и из JSON."""
	if hasattr(data, 'getlist'):
		return data.getlist(key)
	value = data.get(key, [])
	return value if isinstance(value, list) else [value]


def render_cards(request, posts):
	"""Карточки постов тем же шаблоном, что и в ленте (с лайками и прочими аннотациями)."""
	pks = [post.pk for post in posts]
	fresh = {post.pk: post for post in Post.objects.for_feed(request.user).filter(pk__in=pks)}
	return render(request, PAGE_TEMPLATE, {"posts": [fresh[pk] for pk in pks if pk in fresh]})


@api_view(['POST'])
def create_post(request):
	"""Новый пост или ответ: текст и до 4 картинок
	(multipart: text, images[], alt[] в том же порядке, reply_to — id поста, если это ответ)."""
	data = request.data
	text = data.get('text')
	reply_to = None
	if data.get('reply_to'):
		try:
			reply_to_id = uuid.UUID(str(data.get('reply_to')))
		except ValueError:
			return Response({'errors': ['Пост, на который вы отвечаете, не найден.']}, status=status.HTTP_400_BAD_REQUEST)
		# Ответить можно только на пост, который пользователь видит.
		reply_to = Post.objects.visible_to(request.user).filter(pk=reply_to_id).first()
		if reply_to is None:
			return Response({'errors': ['Пост, на который вы отвечаете, удалён или недоступен.']}, status=status.HTTP_404_NOT_FOUND)
	try:
		post = publish_post(
			request.user.profile,
			text if isinstance(text, str) else '',
			request.FILES.getlist('images'),
			_getlist(data, 'alt'),
			reply_to=reply_to,
		)
	except ValidationError as error:
		return Response({'errors': error.messages}, status=status.HTTP_400_BAD_REQUEST)
	return render_cards(request, [post])


@api_view(['GET'])
def profiles_list(request):
	"""
	List profiles.
	"""
	nextPage = 1
	previousPage = 1
	profiles = Profile.objects.select_related('user').order_by('pk')
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
		profile = Profile.objects.select_related('user').get(pk=pk)
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
