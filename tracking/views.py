import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from azzb.htmx import htmx_login_required, is_htmx, trigger
from azzb.ratelimit import rate_limit
from post.models import Post

from . import services
from .models import InteractionEvent, NegativeFeedback


@require_POST
@rate_limit('events', '20/m', '600/h')
def events(request):
	"""Пачка событий из браузера (frontend/js/tracker.js). Гостю и без согласия — 204 без записи."""
	if not request.user.is_authenticated:
		return HttpResponse(status=204)
	try:
		items = json.loads(request.body or b'[]')
	except ValueError:
		return JsonResponse({'errors': ['Неверный формат']}, status=400)
	services.ingest(request, items)
	return HttpResponse(status=204)


TOASTS = {
	NegativeFeedback.Kind.POST: 'Этот пост больше не появится в ваших лентах',
	NegativeFeedback.Kind.AUTHOR: 'Посты @{author} больше не появятся в «Свежем» и «Горячем»',
	NegativeFeedback.Kind.TAG: 'Посты с #{tag} больше не появятся в «Свежем» и «Горячем»',
}


@require_POST
@htmx_login_required
@rate_limit('not-interested', '30/m', '300/h')
def not_interested(request, pk):
	"""«Не интересно» из меню поста: сам пост, его автор или тема (тег). Снять — в настройках."""
	post = get_object_or_404(Post.objects.visible_to(request.user).select_related('author__user'), pk=pk)
	kind = request.POST.get('what')
	if kind not in NegativeFeedback.Kind.values or post.author.user_id == request.user.pk:
		return HttpResponse(status=400)
	target = {}
	if kind == NegativeFeedback.Kind.POST:
		target['post'] = post
	elif kind == NegativeFeedback.Kind.AUTHOR:
		target['author'] = post.author
	else:
		tag = post.hashtags.filter(name=request.POST.get('tag', '')).first()
		if tag is None:
			return HttpResponse(status=400)
		target['tag'] = tag
	NegativeFeedback.objects.get_or_create(user=request.user, kind=kind, **target)
	tag = target.get('tag')
	services.record(
		request, InteractionEvent.Kind.NOT_INTERESTED, post=post, target=post.author.user,
		surface=services.surface_from_referer(request), reason=kind, **({'tag': tag.name} if tag else {}),
	)
	message = TOASTS[kind].format(author=post.author.user.username, tag=tag.name if tag else '')
	if not is_htmx(request):
		messages.success(request, message)
		return redirect(request.headers.get('Referer') or 'index')
	return trigger(HttpResponse(status=204), {'azzb:toast': message, 'azzb:hide-post': {'id': str(post.pk)}})


@require_POST
@login_required
def forget_not_interested(request, pk):
	"""Снять отметку «Не интересно» (настройки → «Блокировки и заглушённые»)."""
	NegativeFeedback.objects.filter(user=request.user, pk=pk).delete()
	return redirect('blocked-accounts')
