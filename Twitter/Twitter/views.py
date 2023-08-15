from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, Http404
from django.template import loader
from django.template.response import TemplateResponse

from .models import Post

def index(request):
	post_thumbs_field = "post_thumbs"
	post_obj = Post.objects.first()
	post_thumbs = getattr(post_obj, post_thumbs_field).split(";")

	latest_posts = Post.objects.order_by("-post_date")[:5]
	context = {"latest_posts": latest_posts, "post_thumbs_as_images": post_thumbs}
	return render(request, "twitter/twitter_indexPage.html", context)

def postThumbsTuple(request, template_name="twitter/twitter_post.html"):
	post_thumbs_field = "post_thumbs"
	post_obj = Post.objects.first()
	post_thumbs = getattr(post_obj, post_thumbs_field).split(";")

	context = {"post_thumbs_as_images": post_thumbs}
	
	return TemplateResponse(request, template_name, context)