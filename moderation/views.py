"""Жалобы, очередь модерации и экран бана (E4)."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.models import Profile
from azzb.ratelimit import rate_limit
from post.models import Post

from . import services
from .forms import ActionForm, ReportForm
from .models import Report

QUEUE_LIMIT = 200
REPORT_RATES = ('10/h', '30/d')
REPORT_LIMIT_MESSAGE = 'Слишком много жалоб подряд. Попробуйте позже.'


def _safe_next(request, fallback):
	next_url = request.POST.get('next') or request.GET.get('next')
	if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
		return next_url
	return fallback


def _report(request, *, post=None, profile):
	fallback = reverse('post', args=[post.pk]) if post else reverse('profile', args=[profile.user.username])
	back = _safe_next(request, fallback)
	if profile.user_id == request.user.pk:
		messages.info(request, 'На себя пожаловаться нельзя.')
		return redirect(back)
	form = ReportForm(request.POST or None)
	if request.method == 'POST' and form.is_valid():
		services.report(request.user.profile, form.cleaned_data['reason'], form.cleaned_data['comment'], post=post, profile=profile)
		messages.success(request, 'Спасибо! Модераторы посмотрят жалобу.')
		return redirect(back)
	return render(request, 'moderation/report.html', {'form': form, 'post': post, 'target': profile, 'back': back})


@login_required
@rate_limit('report', *REPORT_RATES, message=REPORT_LIMIT_MESSAGE)
def report_post(request, pk):
	post = get_object_or_404(Post.objects.visible_to(request.user).select_related('author__user'), pk=pk)
	return _report(request, post=post, profile=post.author)


@login_required
@rate_limit('report', *REPORT_RATES, message=REPORT_LIMIT_MESSAGE)
def report_profile(request, username):
	profile = get_object_or_404(Profile.objects.select_related('user'), user__username=username)
	return _report(request, profile=profile)


def _moderator_only(request):
	# Посторонним — 404: незачем показывать, что такая страница есть.
	if not services.can_moderate(request.user):
		raise Http404


def queue(request):
	"""Очередь: открытые жалобы, сгруппированные по цели (пост или профиль), старые сверху."""
	_moderator_only(request)
	reports = (
		Report.objects.filter(status=Report.Status.OPEN)
		.select_related('reporter__user', 'profile__user', 'post__author__user')
		.prefetch_related('post__images')
		.order_by('created_at')[:QUEUE_LIMIT]
	)
	groups = {}
	for item in reports:
		key = ('post', item.post_id) if item.post_id else ('profile', item.profile_id)
		group = groups.setdefault(key, {'post': item.post, 'profile': item.profile, 'reports': [], 'reasons': {}})
		group['reports'].append(item)
		label = item.get_reason_display()
		group['reasons'][label] = group['reasons'].get(label, 0) + 1
	return render(request, 'moderation/queue.html', {
		'groups': list(groups.values()),
		'ban_terms': [(key, label) for key, (label, _) in services.BAN_TERMS.items()],
	})


@require_POST
def act(request):
	_moderator_only(request)
	form = ActionForm(request.POST)
	if not form.is_valid():
		messages.error(request, ' '.join(error for errors in form.errors.values() for error in errors))
		return redirect('moderation-queue')
	data = form.cleaned_data
	profile = get_object_or_404(Profile.objects.select_related('user'), pk=data['profile'])
	post = get_object_or_404(Post, pk=data['post']) if data.get('post') else None
	reason = data.get('reason', '').strip()
	if data['action'] == 'dismiss':
		services.dismiss(request.user, post=post, profile=None if post else profile)
		messages.success(request, 'Жалобы отклонены')
	elif data['action'] == 'hide':
		services.hide_post(request.user, post, reason)
		messages.success(request, 'Пост скрыт')
	elif data['action'] == 'ban':
		if profile.user_id == request.user.pk or profile.user.is_superuser:
			messages.error(request, 'Этот аккаунт забанить нельзя.')
		else:
			services.ban_user(request.user, profile.user, reason, data['term'])
			messages.success(request, f'@{profile.user.username} забанен(а)')
	return redirect('moderation-queue')


@require_POST
def unban(request, username):
	_moderator_only(request)
	profile = get_object_or_404(Profile.objects.select_related('user'), user__username=username)
	services.unban_user(request.user, profile.user)
	messages.success(request, f'Бан @{username} снят')
	return redirect('profile', slug=username)


@require_POST
def unhide(request, pk):
	_moderator_only(request)
	post = get_object_or_404(Post, pk=pk)
	services.unhide_post(post)
	messages.success(request, 'Пост снова виден всем')
	return redirect(_safe_next(request, reverse('moderation-queue')))
