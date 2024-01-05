from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.shortcuts import render
from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from customUser.serializers import ProfileSerializer
from customUser.models import Profile
from post.serializer import PostSerializer

# @login_required()
#def create_post(request):
#	if request.method == 'POST':
#		user = request.user.username
#		text = request.POST['text']
#
#		new_post = Post.objects.create(user=user, text=text)
#		new_post.save()
#	else:
#		pass
@api_view(['POST',])
def create_post(request):
	serializer = PostSerializer(data={**request.data, "author": request.user.id})
	if serializer.is_valid():
		new_post = serializer.save()
		return render(request, "post/post.html", {"post": new_post})
	return HttpResponse(data=serializer.errors, status=400)

@api_view(['GET', 'POST'])
def profiles_list(request):
	"""
	List profiles.
	"""
	if request.method == 'GET':
		data = []
		nextPage = 1
		previousPage = 1
		profiles = Profile.objects.all()
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

@api_view(['GET', 'PUT', 'DELETE'])
def profile_details(request, pk):
	"""
	Retrieve, update or delete profile by id/pk.
	"""
	try:
		profile = Profile.objects.get(pk=pk)
	except Profile.DoesNotExist:
		return Response(status=status.HTTP_404_NOT_FOUND)
	if request.method == 'GET':
		serializer = ProfileSerializer(profile, context={'request': request})
		return Response(serializer.data)
	
	elif request.method == 'PUT':
		serializer = ProfileSerializer(profile, data=request.data,context={'request': request})
		if serializer.is_valid():
			serializer.save()
			return Response(serializer.data)
		return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

	elif request.method == 'DELETE':
		profile.delete()
		return Response(status=status.HTTP_204_NO_CONTENT)


#class PostAPIView(APIView):
#	def get(self, request):
#		pass
#	def post(self, request):
#		serializer = PostSerializer(data={**request.data, "author": request.user.id})
#		if serializer.is_valid():
#			serializer.save()
#			return JsonResponse(serializer.data, status=201)
#		return JsonResponse(serializer.errors, status=400)