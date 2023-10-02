import json
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.response import Response
from rest_framework.parsers import JSONParser
from rest_framework.renderers import JSONRenderer, TemplateHTMLRenderer
from rest_framework import status

from .serializer import PostSerializer
from azzb.models import Post

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
@api_view(('POST',))
def create_post(request):
	serializer = PostSerializer(data={**request.data, "author": request.user.id})
	if serializer.is_valid():
		new_post = serializer.save()
		return render(request, "azzb/twitter_post.html", {"post": new_post})
	return HttpResponse(data=serializer.errors, status=400)
#class PostAPIView(APIView):
#	def get(self, request):
#		pass
#	def post(self, request):
#		serializer = PostSerializer(data={**request.data, "author": request.user.id})
#		if serializer.is_valid():
#			serializer.save()
#			return JsonResponse(serializer.data, status=201)
#		return JsonResponse(serializer.errors, status=400)