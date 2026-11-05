from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.shortcuts import render
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from customUser.serializers import ProfileSerializer
from customUser.models import Profile
from post.serializer import PostSerializer

@api_view(['POST'])
def create_post(request):
	serializer = PostSerializer(data=request.data)
	if serializer.is_valid():
		new_post = serializer.save(author=request.user.profile)
		return render(request, "post/post.html", {"post": new_post})
	return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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
