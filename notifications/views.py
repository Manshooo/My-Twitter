from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from accounts.models import FollowRequest, Profile
from azzb.htmx import htmx_login_required, is_htmx
from dm.services import unread_count as unread_messages

from .models import Notification
from .services import grouped_page, mark_all_read, parse_before, unread_count


# Вкладка «Упоминания»: события, где к человеку обращаются, — на них отвечают.
MENTION_VERBS = (Notification.Verb.REPLY, Notification.Verb.QUOTE, Notification.Verb.MENTION)


@login_required
def notifications_page(request):
	tab = 'mentions' if request.GET.get('tab') == 'mentions' else 'all'
	before = parse_before(request.GET.get('before'))
	groups, next_before = grouped_page(request.user, before, verbs=MENTION_VERBS if tab == 'mentions' else None)
	# Прочитанным считается всё, что пришло до открытия страницы; подсветка новых уже посчитана выше.
	mark_all_read(request.user)
	add_section_titles(groups, before)
	params = {'before': next_before.isoformat()} if next_before else None
	if params and tab == 'mentions':
		params['tab'] = tab
	context = {'groups': groups, 'next_url': f"{request.path}?{urlencode(params)}" if params else None}
	if is_htmx(request):
		return render(request, 'notifications/_page.html', context)
	me = request.user.profile
	requests = FollowRequest.objects.filter(target=me, requester__in=Profile.objects.public()).count()
	context.update({'tab': tab, 'requests': requests, 'show_requests': me.is_private or requests})
	return render(request, 'notifications/list.html', context)


def add_section_titles(groups, before):
	"""Заголовки «Сегодня» и «Ранее» над первой группой каждого раздела. Порция «Показать ещё»
	продолжает раздел, на котором кончилась предыдущая (её граница — before)."""
	today = timezone.localdate()
	shown = None if before is None else ('today' if timezone.localdate(before) == today else 'earlier')
	for group in groups:
		section = 'today' if timezone.localdate(group['latest']) == today else 'earlier'
		group['section_title'] = None if section == shown else ('Сегодня' if section == 'today' else 'Ранее')
		shown = section


@htmx_login_required
def unread_badge(request):
	"""Значки «Уведомления» и «Сообщения» через hx-swap-oob: по сигналу из сокета или опросом раз в 30 с."""
	return render(request, 'notifications/_badges.html', {
		'unread_notifications': unread_count(request.user),
		'unread_messages': unread_messages(request.user.profile),
	})
