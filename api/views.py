from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.shortcuts import render
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from django.core.exceptions import ValidationError

from customUser.serializers import ProfileSerializer
from customUser.models import Profile
from post.services import find_reply_target, publish_post
from azzb.activity import Action, record
from azzb.ratelimit import rate_limit
from post.views import POST_RATES, render_cards

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
	(multipart: text, images[], alt[] в том же порядке, reply_to — id поста, если это ответ)."""
	data = request.data
	text = data.get('text')
	try:
		post = publish_post(
			request.user.profile,
			text if isinstance(text, str) else '',
			request.FILES.getlist('images'),
			_getlist(data, 'alt'),
			reply_to=find_reply_target(request.user, data.get('reply_to')),
		)
	except ValidationError as error:
		code = status.HTTP_404_NOT_FOUND if getattr(error, 'code', None) == 'not_found' else status.HTTP_400_BAD_REQUEST
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
