import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import OuterRef, Subquery
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from azzb.activity import Action, record
from azzb.htmx import htmx_errors, htmx_login_required, is_htmx, trigger
from azzb.ratelimit import rate_limit
from tracking import services as tracking
from tracking.models import InteractionEvent

from .models import Bookmark, Hashtag, Post
from .pagination import PAGE_TEMPLATE, cursor_page, is_load_more, page_url
from .services import (
	delete_post as soft_delete_post, edit_post, find_post_target, find_reply_target, original, publish_post,
	toggle_bookmark, toggle_like, toggle_pin, toggle_repost, vote,
)


def render_cards(request, posts):
	"""Карточки постов тем же шаблоном, что и в ленте (с лайками, ответами и прочими аннотациями)."""
	pks = [post.pk for post in posts]
	fresh = {post.pk: post for post in Post.objects.for_feed(request.user).filter(pk__in=pks)}
	return render(request, PAGE_TEMPLATE, {"posts": [fresh[pk] for pk in pks if pk in fresh]})


def visible_post(request, pk):
	"""Пост, который пользователь видит, — иначе 404. Лайкнуть, ответить или удалить можно только такой."""
	return get_object_or_404(Post.objects.visible_to(request.user), pk=pk)


def visible_original(request, pk):
	"""Как visible_post, но репост заменяется исходным постом: лайк и репост достаются ему."""
	return original(get_object_or_404(Post.objects.visible_to(request.user).select_related('repost_of'), pk=pk))


# ---------- Страницы и действия на них (HTMX) ----------

# Лимиты (E2): общие для страниц и API, см. azzb/ratelimit.py.
POST_RATES = ('8/m', '60/h')
ERROR_STATUS = {'not_found': 404, 'forbidden': 403}
LIKE_RATES = ('60/m', '600/h')


@require_POST
@htmx_login_required
@rate_limit('like', *LIKE_RATES)
def like_post(request, pk):
	"""Лайк или снятие лайка. htmx заменяет кнопку на ту, что вернулась отсюда."""
	post = visible_original(request, pk)
	liked, total = toggle_like(post, request.user.profile)
	if not liked:
		tracking.record(request, InteractionEvent.Kind.UNLIKE, post=post)
	if not is_htmx(request):
		return redirect('post', pk=post.pk)
	return render(request, 'post/_like.html', {'post': post, 'liked': liked, 'likes_total': total})


@require_POST
@htmx_login_required
@rate_limit('bookmark', *LIKE_RATES)
def bookmark_post(request, pk):
	"""Закладка или её снятие. htmx заменяет кнопку на ту, что вернулась отсюда."""
	post = visible_original(request, pk)
	bookmarked = toggle_bookmark(post, request.user.profile)
	if not is_htmx(request):
		return redirect('post', pk=post.pk)
	response = render(request, 'post/_bookmark.html', {'post': post, 'bookmarked': bookmarked})
	return trigger(response, {'azzb:toast': 'Добавлено в закладки' if bookmarked else 'Убрано из закладок'})


@require_POST
@htmx_login_required
@rate_limit('like', *LIKE_RATES)
def vote_poll(request, pk):
	"""Голос в опросе (B7). htmx заменяет блок опроса на результаты."""
	post = visible_original(request, pk)
	try:
		vote(post, request.user.profile, request.POST.get('option', ''))
	except ValidationError as error:
		return htmx_errors(error.messages)
	if not is_htmx(request):
		return redirect('post', pk=post.pk)
	fresh = Post.objects.for_feed(request.user).get(pk=post.pk)
	return render(request, 'post/_poll_fragment.html', {'post': fresh})


@require_POST
@htmx_login_required
def pin_post(request, pk):
	"""Закрепить свой пост в профиле или открепить (B8). Страница обновляется: меняется порядок
	на вкладке «Посты» и пункт меню у всех карточек."""
	post = visible_post(request, pk)
	if post.author_id != request.user.id or post.is_repost:
		return htmx_errors('Закрепить можно только свой пост.', status=403)
	pinned = toggle_pin(post, request.user.profile)
	if not is_htmx(request):
		return redirect('profile', slug=request.user.username)
	# Тост — через messages: он переживёт перезагрузку страницы (HX-Refresh).
	messages.success(request, 'Пост закреплён в профиле' if pinned else 'Пост откреплён')
	response = HttpResponse()
	response['HX-Refresh'] = 'true'
	return response


@login_required
def bookmarks(request):
	"""Мои закладки, от новых к старым по времени закладки. Только посты, которые я всё ещё вижу."""
	mine = Bookmark.objects.filter(post_id=OuterRef('pk'), profile=request.user.profile).values('created_at')[:1]
	queryset = Post.objects.for_feed(request.user).annotate(bookmarked_at=Subquery(mine)).filter(bookmarked_at__isnull=False)
	posts, cursor = cursor_page(queryset, request.GET.get('cursor'), field='bookmarked_at')
	next_url = page_url(request, cursor=cursor) if cursor else None
	if is_load_more(request):
		return render(request, PAGE_TEMPLATE, {'posts': posts, 'next_url': next_url})
	return render(request, 'post/bookmarks.html', {'posts': posts, 'next_url': next_url})


def hashtag(request, name):
	"""Посты с тегом, от новых к старым, вместе с ответами. Открыта и гостям: на тег ссылаются."""
	if name != name.lower():
		# Теги хранятся в нижнем регистре: один адрес на тег, без дублей в поиске.
		return redirect('hashtag', name=name.lower(), permanent=True)
	tag = Hashtag.objects.filter(name=name.lower()).first()
	queryset = Post.objects.none()
	if tag is not None:
		queryset = Post.objects.for_feed(request.user).without_muted(request.user).filter(hashtags=tag)
	posts, cursor = cursor_page(queryset, request.GET.get('cursor'))
	next_url = page_url(request, cursor=cursor) if cursor else None
	if is_load_more(request):
		return render(request, PAGE_TEMPLATE, {'posts': posts, 'next_url': next_url})
	return render(request, 'post/hashtag.html', {'name': name.lower(), 'posts': posts, 'next_url': next_url})


@require_POST
@htmx_login_required
@rate_limit('post', *POST_RATES)
def repost_post(request, pk):
	"""Репост или его отмена. htmx заменяет кнопку с меню на ту, что вернулась отсюда."""
	post = visible_original(request, pk)
	if post.hidden_at is not None:
		return htmx_errors('Пост скрыт модератором — его нельзя репостить.', status=403)
	if post.author.is_private and post.author_id != request.user.id:
		return htmx_errors('Пост из закрытого аккаунта нельзя репостить.', status=403)
	reposted, total = toggle_repost(post, request.user.profile)
	record(request, Action.POST_CREATE if reposted else Action.POST_DELETE, post=post)
	if not is_htmx(request):
		return redirect('post', pk=post.pk)
	response = render(request, 'post/_repost.html', {
		'post': post, 'reposted': reposted, 'reposts_total': total, 'key': request.POST.get('key', post.pk),
	})
	return trigger(response, {
		'azzb:toast': 'Репост сделан' if reposted else 'Репост отменён',
		'azzb:reposts': {'id': str(post.pk), 'count': total},
	})


@require_POST
@htmx_login_required
def delete_post(request, pk):
	"""Удаление своего поста (мягкое, см. post.services.delete_posts). Со страницы самого поста
	уводим на главную (HX-Redirect), в ленте — событие azzb:post-deleted: azzb.js убирает
	карточки и уменьшает счётчик ответов."""
	post = visible_post(request, pk)
	if post.author_id != request.user.id:
		return htmx_errors('Удалять можно только свои посты.', status=403)
	reply_of = post.reply_to_id
	soft_delete_post(post)
	record(request, Action.POST_DELETE, post=post)
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
			if post.author_id != request.user.id or post.is_repost:
				return htmx_errors('Редактировать можно только свои посты.', status=403)
			if edit_post(post, data.get('text', '')):
				record(request, Action.POST_EDIT, post=post)
		else:
			post = publish_post(
				request.user.profile,
				data.get('text', ''),
				request.FILES.getlist('images'),
				data.getlist('alt'),
				reply_to=find_reply_target(request.user, data.get('reply_to')),
				quote_of=find_post_target(request.user, data.get('quote_of'), 'quote'),
				poll_options=data.getlist('poll_option'),
				poll_duration=data.get('poll_duration'),
			)
			record(request, Action.POST_CREATE, post=post)
	except ValidationError as error:
		return htmx_errors(error.messages, status=ERROR_STATUS.get(getattr(error, 'code', None), 400))
	return render_cards(request, [post])


THREAD_DEPTH = 20


def thread_ancestors(post, user):
	"""Посты выше по ветке, от корня к родителю; недоступные — заглушками (Post.objects.in_thread).
	Второе значение — обрыв ветки сверху: "deleted", если строку родителя стёрли из базы, иначе None."""
	ancestors = []
	parent_id = post.reply_to_id
	gap = "deleted" if post.is_reply and parent_id is None else None
	while parent_id and len(ancestors) < THREAD_DEPTH:
		parent = Post.objects.in_thread(user).filter(pk=parent_id).first()
		if parent is None:
			gap = "deleted"
			break
		ancestors.append(parent)
		parent_id = parent.reply_to_id
		if parent.is_reply and parent_id is None:
			gap = "deleted"
	ancestors.reverse()
	return ancestors, gap


# Сколько сообщений разговора показывать за раз; дальше — «Показать продолжение».
CONVERSATION_PAGE = 20
REPLIES_TEMPLATE = "post/_replies.html"


def next_in_conversation(post_pk, author_id, partner_id):
	"""Следующее сообщение разговора после поста: (id, автор) или None, и сколько ответов
	на пост остаются в стороне от линии.

	Один ответ — он и есть продолжение. Если ответов несколько, продолжением считаем самый
	ранний ответ самого автора (дописывает мысль) или его собеседника — автора поста выше
	(отвечает обратно). Остальные ответы — в стороне, на них ведёт ссылка. Если ни один
	ответ не подходит, разговор здесь расходится на ветки и линия заканчивается."""
	replies = Post.objects.thread_members().filter(reply_to_id=post_pk).order_by('created_at', 'id')
	first = list(replies.values_list('pk', 'author_id')[:2])
	if len(first) < 2:
		return (first[0] if first else None), 0
	total = replies.count()
	pick = replies.filter(author_id__in={author_id, partner_id} - {None}).values_list('pk', 'author_id').first()
	return pick, total - (1 if pick else 0)


def follow_conversation(start, user, limit=CONVERSATION_PAGE):
	"""Разговор под постом start одной линией (правило — next_in_conversation).

	Возвращает то, что нужно шаблону post/_conversation.html: сообщения после start с числом
	ответов в стороне у каждого, сколько ответов в стороне у самого start и id поста, с которого
	продолжать, если линия длиннее limit. Один лёгкий запрос на шаг и один — за карточками."""
	steps = []
	node, partner = (start.pk, start.author_id), (start.reply_to.author_id if start.reply_to_id else None)
	continue_from = None
	while True:
		following, aside = next_in_conversation(node[0], node[1], partner)
		steps.append((node[0], aside))
		if following is None:
			break
		if len(steps) > limit:
			continue_from = node[0]
			break
		partner, node = node[1], following
	cards = Post.objects.in_thread(user).in_bulk([pk for pk, _ in steps[1:]])
	return {
		"start": start,
		"lead_aside": steps[0][1],
		"rows": [(cards[pk], aside) for pk, aside in steps[1:] if pk in cards],
		"continue_from": continue_from,
	}


# Сколько сообщений ветки под ответом видно сразу; дальше — «Показать продолжение».
BRANCH_PREVIEW = 2


def attach_branches(replies, user, open_single=False):
	"""Ветка под каждым ответом с ответами (вариант B ревизии R2): начало разговора одной линией,
	без вложенности глубже одного уровня. Единственный ответ на странице раскрыт целиком —
	это переписка. Запросы — только для ответов, у которых есть свои ответы."""
	limit = CONVERSATION_PAGE if open_single and len(replies) == 1 else BRANCH_PREVIEW
	for reply in replies:
		reply.branch = follow_conversation(reply, user, limit) if reply.replies_count else None


def post_detail(request, pk):
	"""Страница одного поста /p/<uuid>/: ветка выше, сам пост и ответы на него по времени.
	Открыта и гостям: ссылкой на пост делятся. Недоступный пост (удалён, скрыт, автор
	забанен или в блокировке) показывается заглушкой — ради ответов под ним.
	Под каждым ответом — его ветка (attach_branches)."""
	post = get_object_or_404(Post.objects.in_thread(request.user), pk=pk)
	if post.is_repost:
		# У репоста нет своей страницы: ни текста, ни ответов.
		if post.repost_of_id is None:
			raise Http404
		return redirect('post', pk=post.repost_of_id)
	cursor_in = request.GET.get("cursor")
	replies, cursor = cursor_page(
		Post.objects.in_thread(request.user).filter(reply_to=post), cursor_in, ascending=True,
	)
	next_url = page_url(request, cursor=cursor) if cursor else None
	attach_branches(replies, request.user, open_single=not cursor_in)
	if is_load_more(request):
		return render(request, REPLIES_TEMPLATE, {"posts": replies, "next_url": next_url})
	if post.available:
		tracking.record(request, InteractionEvent.Kind.OPEN, post=post, surface=tracking.surface_from_referer(request))
	ancestors, gap = thread_ancestors(post, request.user)
	# Заглушку недоступного поста показываем ради ответов, но со статусом 404 — для поисковиков это не страница.
	return render(request, "post/detail.html", {
		"post": post,
		"ancestors": ancestors,
		"thread_gap": gap,
		"replies": replies,
		"next_url": next_url,
	}, status=200 if post.available else 404)


def post_conversation(request, pk):
	"""Разговор под постом одной линией — для кнопок «Показать ветку» и «Показать продолжение»
	(?more=1: начало линии уже на странице, ссылку на ответы в стороне у него не повторяем).
	Без htmx — просто страница поста: там разговор под единственным ответом раскрыт и так."""
	if not is_htmx(request):
		return redirect('post', pk=pk)
	start = get_object_or_404(Post.objects.in_thread(request.user), pk=pk)
	conversation = follow_conversation(start, request.user)
	if request.GET.get("more"):
		conversation["lead_aside"] = 0
	return render(request, "post/_conversation.html", {"conversation": conversation})


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
	liked, total = toggle_like(original(post), request.user.profile)
	return Response({"likes_count": total, "liked": liked})


@api_view(['POST'])
def delete(request):
	post = _post_from_request(request)
	if post is None:
		return Response({'id': 'Нужен id поста.'}, status=status.HTTP_400_BAD_REQUEST)
	if post.author_id != request.user.id:
		return Response(status=status.HTTP_403_FORBIDDEN)
	soft_delete_post(post)
	record(request, Action.POST_DELETE, post=post)
	return Response(status=status.HTTP_200_OK)


@rate_limit('post', *POST_RATES)
@api_view(['POST'])
def edit(request):
	"""Новый текст своего поста: {"id": ..., "text": ...}. Отдаёт обновлённую карточку."""
	post = _post_from_request(request)
	if post is None:
		return Response({'errors': ['Нужен id поста.']}, status=status.HTTP_400_BAD_REQUEST)
	if post.author_id != request.user.id or post.is_repost:
		return Response({'errors': ['Редактировать можно только свои посты.']}, status=status.HTTP_403_FORBIDDEN)
	text = request.data.get('text')
	try:
		if edit_post(post, text if isinstance(text, str) else ''):
			record(request, Action.POST_EDIT, post=post)
	except ValidationError as error:
		return Response({'errors': error.messages}, status=status.HTTP_400_BAD_REQUEST)
	return render_cards(request, [post])
