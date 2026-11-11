from datetime import datetime
from urllib.parse import urlencode

from django.contrib import messages as flash
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import Profile
from azzb.htmx import htmx_errors, htmx_login_required, is_htmx, trigger
from azzb.ratelimit import rate_limit
from notifications.services import unread_count as unread_notifications

from . import services
from .models import MAX_IMAGES, MESSAGE_MAX_LENGTH


def _int(value):
	try:
		return int(value)
	except (TypeError, ValueError):
		return None


def _before(raw):
	try:
		value = datetime.fromisoformat(raw)
	except (TypeError, ValueError):
		return None
	return value if timezone.is_aware(value) else None


def _member(request, pk):
	member = services.get_member(request.user.profile, pk)
	if member is None:
		raise Http404
	return member


def _inbox_context(request):
	members, next_before = services.inbox(request.user.profile, _before(request.GET.get('before')))
	next_url = f"{reverse('dm-inbox')}?{urlencode({'before': next_before.isoformat()})}" if next_before else None
	return {'members': members, 'next_url': next_url}


def _chat_context(request, member, peer):
	"""Переписка (или пустой новый диалог с peer) для правой панели."""
	if member is None:
		return {'peer': peer, 'chat_messages': [], 'refusal': services.refusal(request.user.profile, peer)}
	messages, has_more = services.page(member)
	services.mark_read(member)
	return {
		'member': member,
		'peer': member.peer,
		# Не «messages»: так в шаблонах называются флеш-сообщения Django, оболочка показывает их тостами.
		'chat_messages': messages,
		'has_more': has_more,
		'seen': services.seen_by_peer(member, messages),
		'refusal': services.refusal(member.profile, member.peer, member.conversation),
	}


def _render_inbox(request, chat=None):
	context = {**_inbox_context(request), 'max_images': MAX_IMAGES, 'message_max_length': MESSAGE_MAX_LENGTH}
	if chat:
		context.update(chat)
	return render(request, 'dm/inbox.html', context)


@login_required
def inbox_page(request):
	"""Список диалогов. Для htmx — только список: обновление по сигналу или «Показать ещё»."""
	if is_htmx(request):
		context = {**_inbox_context(request), 'active': _int(request.GET.get('active'))}
		template = 'dm/_list_items.html' if request.GET.get('before') else 'dm/_list.html'
		return render(request, template, context)
	return _render_inbox(request)


@login_required
def conversation_page(request, pk):
	member = _member(request, pk)
	before = _int(request.GET.get('before'))
	if before is not None:
		messages, has_more = services.page(member, before)
		return render(request, 'dm/_older.html', {'member': member, 'chat_messages': messages, 'has_more': has_more})
	return _render_inbox(request, _chat_context(request, member, member.peer))


@htmx_login_required
def conversation_updates(request, pk):
	"""Новые сообщения после ?after=: по сигналу из сокета или опросом. Заодно — «Прочитано» и счётчики."""
	member = _member(request, pk)
	after = _int(request.GET.get('after')) or 0
	messages = services.newer(member, after)
	read = services.mark_read(member)
	recent, _ = services.page(member, size=20)
	return render(request, 'dm/_updates.html', {
		'member': member,
		'chat_messages': messages,
		'seen': services.seen_by_peer(member, recent),
		'badges': read,
		'unread_notifications': unread_notifications(request.user) if read else 0,
		'unread_messages': services.unread_count(member.profile) if read else 0,
	})


def _send(request, recipient, member):
	"""Общая часть отправки: в существующий диалог и первое сообщение."""
	try:
		member, _ = services.send_message(
			request.user.profile, recipient, request.POST.get('text', ''), request.FILES.getlist('images'), member=member,
		)
	except ValidationError as error:
		if is_htmx(request):
			return htmx_errors(error.messages)
		for message in error.messages:
			flash.error(request, message)
		return None
	return member


@require_POST
@login_required
@rate_limit('dm', '20/m', '300/h', message='Слишком много сообщений подряд. Подождите немного.')
def send(request, pk):
	member = _member(request, pk)
	result = _send(request, member.peer, member)
	if isinstance(result, HttpResponse):
		return result
	url = reverse('dm-conversation', args=[member.conversation_id])
	if is_htmx(request):
		# Сообщение вставит обычный запрос новых (dm/_updates.html): у вкладки один путь вставки.
		return trigger(HttpResponse(status=204), {'azzb:dm-sent': True})
	return redirect(url)


@login_required
@rate_limit('dm-start', '20/h', '60/d', message='Слишком много новых диалогов. Попробуйте позже.')
def start(request, username):
	"""«Написать» из профиля: открыть диалог, а если его нет — пустой, он появится с первым сообщением."""
	me = request.user.profile
	peer = get_object_or_404(Profile.objects.public().select_related('user'), user__username=username)
	if peer.pk == me.pk:
		return redirect('dm-inbox')
	member = services.find_member(me, peer)
	if request.method != 'POST':
		if member is not None:
			return redirect('dm-conversation', member.conversation_id)
		return _render_inbox(request, _chat_context(request, None, peer))
	result = _send(request, peer, member)
	if isinstance(result, HttpResponse):
		return result
	if result is None:
		return redirect('dm-start', username)
	url = reverse('dm-conversation', args=[result.conversation_id])
	if is_htmx(request):
		response = HttpResponse(status=204)
		response['HX-Redirect'] = url
		return response
	return redirect(url)


@require_POST
@htmx_login_required
def delete_message(request, pk, message_id):
	member = _member(request, pk)
	services.delete_message(member, message_id)
	message = get_object_or_404(services.visible_messages(member), pk=message_id)
	if is_htmx(request):
		return render(request, 'dm/_message.html', {'message': message, 'me_id': member.profile_id})
	return redirect('dm-conversation', pk)


@require_POST
@login_required
def clear(request, pk):
	services.clear_conversation(_member(request, pk))
	flash.success(request, 'Диалог удалён')
	return redirect('dm-inbox')
