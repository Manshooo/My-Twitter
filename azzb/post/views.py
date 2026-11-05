from django.contrib.auth import get_user_model
from django.shortcuts import HttpResponse, get_object_or_404, render
from django.views.generic.detail import DetailView
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

import json
import uuid

from post.serializer import PostSerializer

from .models import Post

User = get_user_model()

def _post_from_request(request):
	"""Пост по id из тела запроса. Без id или с невалидным UUID — 400, а не 500."""
	try:
		post_id = uuid.UUID(str(request.data['id']))
	except (KeyError, TypeError, ValueError, AttributeError):
		return None
	# Лайкнуть или удалить можно только пост, который пользователю вообще виден.
	return get_object_or_404(Post.objects.visible_to(request.user), pk=post_id)

@api_view(['POST'])
def like(request):
	post = _post_from_request(request)
	if post is None:
		return Response({'id': 'Нужен id поста.'}, status=status.HTTP_400_BAD_REQUEST)
	if post.likes.filter(pk=request.user.profile.id).exists():
		post.likes.remove(request.user.profile.id)
		liked = False
	else:
		post.likes.add(request.user.profile.id)
		liked = True
	likes_count = post.likes.count()

	context = {"likes_count": likes_count, "liked": liked,}

	return HttpResponse(json.dumps(context), content_type='application/json')

@api_view(['POST'])
def delete(request):
	post = _post_from_request(request)
	if post is None:
		return Response({'id': 'Нужен id поста.'}, status=status.HTTP_400_BAD_REQUEST)
	if request.user.id == post.author.user.id:
		post.delete()
		return Response(status=status.HTTP_200_OK)
	else:
		return Response(status=status.HTTP_403_FORBIDDEN)
class PostDetailView(DetailView):
	model = Post
	template_name = "post/post.html"

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["liked"] = False
		if Post.likes.filter(pk=self.request.user.profile.id).exists():
			context["liked"] = True
		return context