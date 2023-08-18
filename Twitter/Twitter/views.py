from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, Http404
from django.template import loader
from django.template.response import TemplateResponse
from django.views.generic.list import ListView
from django.views import generic

from .models import Post, Test

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