from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, Http404
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from django.contrib.auth.decorators import login_required

from .models import Post, Profile

def index(request):
	latest_posts = Post.objects.order_by("-created_at")[:10]
	context = {"latest_posts": latest_posts}
	return render(request, "twitter/twitter_indexPage.html", context)
@login_required()
def create_post(request):
	if request.method == 'POST':
		user = request.user.username
		text = request.POST['text']

		new_post = Post.objects.create(user=user, text=text)
		new_post.save()
	else:
		pass

class PostListView(ListView):
	template_name = "twitter/twitter_post.html"
	model = Post
	context_object_name = "post"
class UserProfileDetailView(DetailView):
	template_name = "registration/profile.html"
	model = Profile
	context_object_name = "profile"
	pk_url_kwarg = "username"
	slug_field = "user__username"