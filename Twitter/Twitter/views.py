from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, Http404
from django.template import loader

from .models import Post

def index(request):
	latest_posts = Post.objects.order_by("-post_date")[:5]
	context = {"latest_posts": latest_posts}
	return render(request, "twitter/twitter_indexPage.html", context)