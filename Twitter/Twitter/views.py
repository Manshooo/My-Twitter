from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, Http404
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.urls import reverse_lazy
from django.views.generic.edit import CreateView
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from django.contrib.auth.decorators import login_required

from .models import Post, Test, Profile
from .forms import UserCreationForm

def my_view(request):
	content = {'message': 'Hello, world!'}
	return Response(content)

def index(request):
	latest_posts = Post.objects.order_by("-post_date")[:5]
	context = {"latest_posts": latest_posts}
	return render(request, "twitter/twitter_indexPage.html", context)

class PostListView(ListView):
	template_name = "twitter/twitter_post.html"
	model = Post
	context_object_name = "post"

class TestListView(ListView):
	template_name = "twitter/twitter_test.html"
	model = Test
	context_object_name = "test"
class UserProfileDetailView(DetailView):
	template_name = "registration/profile.html"
	model = Profile
	context_object_name = "profile"
	pk_url_kwarg = "username"
	slug_field = "user__username"