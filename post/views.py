from django.contrib.auth import get_user_model
from django.shortcuts import HttpResponse, get_object_or_404, render
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

import json
import uuid

from django.core.exceptions import ValidationError

from .models import Post
from .services import edit_post
from .pagination import PAGE_TEMPLATE, cursor_page, is_load_more, page_url

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
THREAD_DEPTH = 20


def thread_ancestors(post, user):
	"""Посты выше по ветке, от корня к родителю. Второе значение — обрыв ветки сверху:
	"deleted" (родителя удалили), "hidden" (родитель недоступен) или None."""
	ancestors = []
	parent_id = post.reply_to_id
	gap = "deleted" if post.is_reply and parent_id is None else None
	while parent_id and len(ancestors) < THREAD_DEPTH:
		parent = Post.objects.for_feed(user).filter(pk=parent_id).first()
		if parent is None:
			gap = "hidden"
			break
		ancestors.append(parent)
		parent_id = parent.reply_to_id
		if parent.is_reply and parent_id is None:
			gap = "deleted"
	ancestors.reverse()
	return ancestors, gap


@api_view(['POST'])
def edit(request):
	"""Новый текст своего поста: {"id": ..., "text": ...}. Отдаёт обновлённую карточку."""
	post = _post_from_request(request)
	if post is None:
		return Response({'errors': ['Нужен id поста.']}, status=status.HTTP_400_BAD_REQUEST)
	if post.author_id != request.user.id:
		return Response({'errors': ['Редактировать можно только свои посты.']}, status=status.HTTP_403_FORBIDDEN)
	text = request.data.get('text')
	try:
		edit_post(post, text if isinstance(text, str) else '')
	except ValidationError as error:
		return Response({'errors': error.messages}, status=status.HTTP_400_BAD_REQUEST)
	fresh = Post.objects.for_feed(request.user).get(pk=post.pk)
	return render(request, PAGE_TEMPLATE, {"posts": [fresh]})


def post_detail(request, pk):
	"""Страница одного поста /p/<uuid>/: ветка выше, сам пост и ответы на него по времени.
	Открыта и гостям: ссылкой на пост делятся."""
	post = get_object_or_404(Post.objects.for_feed(request.user), pk=pk)
	replies, cursor = cursor_page(
		Post.objects.for_feed(request.user).filter(reply_to=post), request.GET.get("cursor"), ascending=True,
	)
	next_url = page_url(request, cursor=cursor) if cursor else None
	if is_load_more(request):
		return render(request, PAGE_TEMPLATE, {"posts": replies, "next_url": next_url})
	ancestors, gap = thread_ancestors(post, request.user)
	return render(request, "post/detail.html", {
		"post": post,
		"ancestors": ancestors,
		"thread_gap": gap,
		"replies": replies,
		"next_url": next_url,
	})
