from django.contrib.auth import get_user_model
from django.shortcuts import HttpResponse, get_object_or_404, render
from django.views.generic.detail import DetailView
from rest_framework.decorators import api_view

import json

from post.serializer import PostSerializer

from .models import Post

User = get_user_model()

@api_view(['POST',])
def like(request):
	# profile.user_id = user.id (=user?)
	if request.method == 'POST':
		data = request.data
		id = data['id']
		post = get_object_or_404(Post, pk=id)
		if post.likes.filter(pk=request.user.profile.id).exists():
			post.likes.remove(request.user.profile.id)
			likes_count = Post.objects.get(pk=id).likes_count
			liked = False
		else:
			post.likes.add(request.user.profile.id)
			likes_count = Post.objects.get(pk=id).likes_count
			liked = True

	context = {"likes_count": likes_count, "liked": liked,}

	return HttpResponse(json.dumps(context), content_type='application/json')

class PostDetailView(DetailView):
	model = Post
	template_name = "post/post.html"

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["liked"] = False
		if Post.likes.filter(pk=self.request.user.profile.id).exists():
			context["liked"] = True
		return context