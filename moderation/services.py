"""Действия модерации (E4): жалоба, скрытие поста, бан. Одна точка для очереди и админки."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from customUser.models import BAN_FOREVER

from .models import Ban, Report

User = get_user_model()

# Сроки бана в очереди модерации: значение формы → (подпись, длительность; None — навсегда).
BAN_TERMS = {
	'1d': ('1 день', timedelta(days=1)),
	'7d': ('7 дней', timedelta(days=7)),
	'30d': ('30 дней', timedelta(days=30)),
	'forever': ('навсегда', None),
}


def can_moderate(user):
	"""Право moderation.moderate — напрямую или через группу «Модераторы».

	Одним запросом и с запоминанием на объекте пользователя: проверка нужна на каждой странице
	(пункт «Модерация» в меню), а user.has_perm делает два запроса."""
	if not user.is_authenticated:
		return False
	if user.is_superuser:
		return True
	if not hasattr(user, '_can_moderate'):
		user._can_moderate = Permission.objects.filter(
			content_type__app_label='moderation', codename='moderate',
		).filter(Q(group__user=user) | Q(user=user)).exists()
	return user._can_moderate


def report(reporter, reason, comment='', post=None, profile=None):
	"""Новая жалоба или обновление открытой жалобы того же человека на ту же цель."""
	if post is not None:
		profile = post.author
	report, _ = Report.objects.update_or_create(
		reporter=reporter, post=post, profile=profile, status=Report.Status.OPEN,
		defaults={'reason': reason, 'comment': comment.strip()[:500]},
	)
	return report


def _close_reports(reports, status, moderator, resolution):
	return reports.filter(status=Report.Status.OPEN).update(
		status=status, resolved_at=timezone.now(), resolved_by=moderator, resolution=resolution[:200],
	)


def open_reports_for(post=None, profile=None):
	"""Открытые жалобы на цель: на пост — только на него; на профиль — на профиль и все его посты."""
	if post is not None:
		return Report.objects.filter(post=post)
	return Report.objects.filter(profile=profile)


def dismiss(moderator, post=None, profile=None, note='Нарушений нет'):
	return _close_reports(open_reports_for(post, profile), Report.Status.DISMISSED, moderator, note)


@transaction.atomic
def hide_post(moderator, post, reason):
	post.hidden_at = timezone.now()
	post.hidden_reason = reason[:200]
	post.save(update_fields=['hidden_at', 'hidden_reason'])
	_close_reports(Report.objects.filter(post=post), Report.Status.RESOLVED, moderator, f'Пост скрыт: {reason}')


def unhide_post(post):
	post.hidden_at = None
	post.hidden_reason = ''
	post.save(update_fields=['hidden_at', 'hidden_reason'])


@transaction.atomic
def ban_user(moderator, user, reason, term='forever'):
	"""Бан на срок из BAN_TERMS. Посты забаненного пропадают у всех (Post.objects.visible_to),
	сам он видит только экран «Аккаунт заблокирован». Закрывает все открытые жалобы на него."""
	label, duration = BAN_TERMS[term]
	until = timezone.now() + duration if duration else None
	Ban.objects.create(user=user, reason=reason, until=until, created_by=moderator)
	user.banned_until = until or BAN_FOREVER
	user.ban_reason = reason[:500]
	user.save(update_fields=['banned_until', 'ban_reason'])
	_close_reports(
		Report.objects.filter(Q(profile__user=user)), Report.Status.RESOLVED, moderator, f'Бан {label}: {reason}',
	)


@transaction.atomic
def unban_user(moderator, user):
	Ban.objects.filter(user=user, lifted_at__isnull=True).filter(
		Q(until__isnull=True) | Q(until__gt=timezone.now()),
	).update(lifted_at=timezone.now(), lifted_by=moderator)
	user.banned_until = None
	user.ban_reason = ''
	user.save(update_fields=['banned_until', 'ban_reason'])
