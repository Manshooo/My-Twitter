from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from azzb.htmx import htmx_login_required, is_htmx

from .services import grouped_page, mark_all_read, parse_before, unread_count


@login_required
def notifications_page(request):
	groups, next_before = grouped_page(request.user, parse_before(request.GET.get('before')))
	# Прочитанным считается всё, что пришло до открытия страницы; подсветка новых уже посчитана выше.
	mark_all_read(request.user)
	context = {
		'groups': groups,
		'next_url': f"{request.path}?{urlencode({'before': next_before.isoformat()})}" if next_before else None,
	}
	if is_htmx(request):
		return render(request, 'notifications/_page.html', context)
	return render(request, 'notifications/list.html', context)


@htmx_login_required
def unread_badge(request):
	"""Опрос раз в 30 с из оболочки: значки обновляются через hx-swap-oob."""
	return render(request, 'notifications/_badges.html', {'unread_notifications': unread_count(request.user)})
