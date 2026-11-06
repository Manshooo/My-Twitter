import uuid

from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from azzb.htmx import htmx_errors, htmx_login_required, is_htmx, trigger
from azzb.ratelimit import rate_limit

from .models import Post
from .pagination import PAGE_TEMPLATE, cursor_page, is_load_more, page_url
from .services import edit_post, find_reply_target, publish_post, toggle_like


def render_cards(request, posts):
	"""Карточки постов тем же шаблоном, что и в ленте (с лайками, ответами и прочими аннотациями)."""
	pks = [post.pk for post in posts]
	fresh = {post.pk: post for post in Post.objects.for_feed(request.user).filter(pk__in=pks)}
	return render(request, PAGE_TEMPLATE, {"posts": [fresh[pk] for pk in pks if pk in fresh]})


def visible_post(request, pk):
	"""Пост, который пользователь видит, — иначе 404. Лайкнуть, ответить или удалить можно только такой."""
	return get_object_or_404(Post.objects.visible_to(request.user), pk=pk)


# ---------- Страницы и действия на них (HTMX) ----------

# Лимиты (E2): общие для страниц и API, см. azzb/ratelimit.py.
POST_RATES = ('8/m', '60/h')
LIKE_RATES = ('60/m', '600/h')


@require_POST
@htmx_login_required
@rate_limit('like', *LIKE_RATES)
def like_post(request, pk):
	"""Лайк или снятие лайка. htmx заменяет кнопку на ту, что вернулась отсюда."""
	post = visible_post(request, pk)
	liked, total = toggle_like(post, request.user.profile)
	if not is_htmx(request):
		return redirect('post', pk=post.pk)
	return render(request, 'post/_like.html', {'post': post, 'liked': liked, 'likes_total': total})


@require_POST
@htmx_login_required
def delete_post(request, pk):
	"""Удаление своего поста. Со страницы самого поста уводим на главную (HX-Redirect),
	в ленте — событие azzb:post-deleted: azzb.js убирает карточки и уменьшает счётчик ответов."""
	post = visible_post(request, pk)
	if post.author_id != request.user.id:
		return htmx_errors('Удалять можно только свои посты.', status=403)
	reply_of = post.reply_to_id
	post.delete()
	if not is_htmx(request):
		return redirect('index')
	response = HttpResponse()
	if request.POST.get('main'):
		response['HX-Redirect'] = reverse('index')
		return response
	# Порядок важен: htmx вызывает события по очереди на кнопке «Удалить», а azzb:post-deleted
	# убирает карточку вместе с ней — событие после него до страницы уже не дойдёт.
	return trigger(response, {
		'azzb:toast': 'Пост удалён',
		'azzb:post-deleted': {'id': str(pk), 'replyOf': str(reply_of) if reply_of else ''},
	})


@require_POST
@htmx_login_required
@rate_limit('post', *POST_RATES)
def compose(request):
	"""Всё, что отправляет composer: новый пост, ответ (reply_to) или правка своего поста (edit).
	Отдаёт карточку; куда её вставить, решает azzb.js — он знает, что сейчас открыто на странице."""
	data = request.POST
	try:
		if data.get('edit'):
			try:
				post = visible_post(request, uuid.UUID(data['edit']))
			except ValueError:
				return htmx_errors('Пост не найден.')
			if post.author_id != request.user.id:
				return htmx_errors('Редактировать можно только свои посты.', status=403)
			edit_post(post, data.get('text', ''))
		else:
			post = publish_post(
				request.user.profile,
				data.get('text', ''),
				request.FILES.getlist('images'),
				data.getlist('alt'),
				reply_to=find_reply_target(request.user, data.get('reply_to')),
			)
	except ValidationError as error:
		return htmx_errors(error.messages, status=404 if getattr(error, 'code', None) == 'not_found' else 400)
	return render_cards(request, [post])


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


# ---------- JSON API (для будущего мобильного клиента, A1) ----------

def _post_from_request(request):
	"""Пост по id из тела запроса. Без id или с невалидным UUID — None (400), а не 500."""
	try:
		post_id = uuid.UUID(str(request.data['id']))
	except (KeyError, TypeError, ValueError, AttributeError):
		return None
	return visible_post(request, post_id)


@rate_limit('like', *LIKE_RATES)
@api_view(['POST'])
def like(request):
	post = _post_from_request(request)
	if post is None:
		return Response({'id': 'Нужен id поста.'}, status=status.HTTP_400_BAD_REQUEST)
	liked, total = toggle_like(post, request.user.profile)
	return Response({"likes_count": total, "liked": liked})


@api_view(['POST'])
def delete(request):
	post = _post_from_request(request)
	if post is None:
		return Response({'id': 'Нужен id поста.'}, status=status.HTTP_400_BAD_REQUEST)
	if post.author_id != request.user.id:
		return Response(status=status.HTTP_403_FORBIDDEN)
	post.delete()
	return Response(status=status.HTTP_200_OK)


@rate_limit('post', *POST_RATES)
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
	return render_cards(request, [post])
