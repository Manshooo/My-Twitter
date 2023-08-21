from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, Http404
from django.template import loader
from django.template.response import TemplateResponse
from django.views.generic.list import ListView
from django.views import generic
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Post, Test


@api_view(['GET'])
@authentication_classes([SessionAuthentication])

def index(request):
	isAuthenticated = request.user.is_authenticated
	latest_posts = Post.objects.order_by("-post_date")[:5]
	context = {"latest_posts": latest_posts, "IsAuthenticated": isAuthenticated}
	return render(request, "twitter/twitter_indexPage.html", context)

class PostListView(ListView):
	template_name = "twitter/twitter_post.html"
	model = Post
	context_object_name = "post"

class TestListView(ListView):
	template_name = "twitter/twitter_test.html"
	model = Test
	context_object_name = "test"

def my_view(request):
    content = {'message': 'Hello, world!'}
    return Response(content)