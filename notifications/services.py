"""Создание, снятие и выборка уведомлений (D1)."""
from datetime import datetime
from django.contrib.postgres.aggregates import ArrayAgg
from django.db import transaction
from django.db.models import Count, Max, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

from accounts.models import Block, Mute, Profile
from azzb.realtime import push
from post.models import Poll, PollVote, Post

from .models import Notification

Verb = Notification.Verb
PAGE_SIZE = 20
# Сколько имён показывать в сгруппированном уведомлении: «Аня, Боря и ещё 3».
NAMES_SHOWN = 2


def notify(recipient, actor, verb, post=None):
	if recipient.pk != actor.pk:
		_, created = Notification.objects.get_or_create(recipient=recipient, actor=actor, verb=verb, post=post)
		if created:
			# F3: значок обновится сразу, а открытая страница уведомлений предложит показать новые.
			push([recipient.user_id], 'notifications')


def retract(recipient, actor, verb, post=None):
	"""Сняли лайк или отписались — уведомление больше не правда."""
	deleted, _ = Notification.objects.filter(recipient=recipient, actor=actor, verb=verb, post=post).delete()
	if deleted:
		push([recipient.user_id], 'badges')


def visible_for(user):
	"""Уведомления, которые пользователь видит. Те же правила, что у постов (visible_to), плюс
	не показываем действия заглушённых и отключённых, удалённых или забаненных."""
	me = user.profile
	return (
		Notification.objects.filter(recipient=me, actor__user__is_active=True)
		.exclude(actor__user__banned_until__gt=timezone.now())
		.exclude(actor__in=Block.objects.filter(blocker=me).values('blocked'))
		.exclude(actor__in=Block.objects.filter(blocked=me).values('blocker'))
		.exclude(actor__in=Mute.objects.filter(muter=me).values('muted'))
		.filter(Q(post__isnull=True) | Q(post__in=Post.objects.visible_to(user).values('pk')))
	)


def notify_ended_polls():
	"""«Опрос завершён» автору и проголосовавшим. Без cron: вызывается при подсчёте непрочитанного,
	то есть при первом же открытии страницы кем-нибудь после окончания опроса."""
	now = timezone.now()
	for poll_id in Poll.objects.filter(closed_at__isnull=True, ends_at__lte=now).values_list('pk', flat=True)[:20]:
		with transaction.atomic():
			# Параллельный запрос мог закрыть этот опрос раньше — тогда рассылает он.
			if not Poll.objects.filter(pk=poll_id, closed_at__isnull=True).update(closed_at=now):
				continue
			post = Post.objects.select_related('author').get(poll__pk=poll_id)
			if post.deleted_at is not None:
				continue
			voters = PollVote.objects.filter(poll_id=poll_id).values_list('profile_id', flat=True)
			recipients = {post.author.pk, *voters}
			Notification.objects.bulk_create(
				[Notification(recipient_id=pk, actor=post.author, verb=Verb.POLL_ENDED, post=post) for pk in recipients],
				ignore_conflicts=True,
			)
			push(Profile.objects.filter(pk__in=recipients).values_list('user_id', flat=True), 'notifications')


def unread_count(user):
	notify_ended_polls()
	return visible_for(user).filter(read_at__isnull=True).count()


def mark_all_read(user):
	if Notification.objects.filter(recipient=user.profile, read_at__isnull=True).update(read_at=timezone.now()):
		push([user.pk], 'badges')  # другие вкладки этого человека


def parse_before(raw):
	try:
		value = datetime.fromisoformat(raw)
	except (TypeError, ValueError):
		return None
	return value if timezone.is_aware(value) else None


def grouped_page(user, before=None, size=PAGE_SIZE, verbs=None):
	"""Страница уведомлений, сгруппированных по (что, пост, день): лайки одного поста за день —
	одна строка «Аня и ещё 5», подписки за день — тоже. Ответ у каждого свой пост, поэтому
	всегда отдельно. verbs — только эти события (вкладка «Упоминания»).
	Возвращает (группы, before для следующей страницы)."""
	events = visible_for(user) if verbs is None else visible_for(user).filter(verb__in=verbs)
	rows = (
		events
		.annotate(day=TruncDate('created_at'))
		.values('verb', 'post_id', 'day')
		.annotate(
			latest=Max('created_at'),
			actor_ids=ArrayAgg('actor_id', order_by='-created_at'),
			unread=Count('pk', filter=Q(read_at__isnull=True)),
		)
		.order_by('-latest')
	)
	if before is not None:
		rows = rows.filter(latest__lt=before)
	rows = list(rows[:size + 1])
	next_before = rows[size - 1]['latest'] if len(rows) > size else None
	rows = rows[:size]

	shown_ids = {pk for row in rows for pk in row['actor_ids'][:NAMES_SHOWN]}
	profiles = Profile.objects.select_related('user').in_bulk(shown_ids)
	post_ids = {row['post_id'] for row in rows if row['post_id']}
	posts = Post.objects.for_feed(user).in_bulk(post_ids)

	groups = []
	for row in rows:
		post = posts.get(row['post_id'])
		if row['post_id'] and post is None:
			continue  # пост пропал между запросами
		actors = [profiles[pk] for pk in row['actor_ids'][:NAMES_SHOWN] if pk in profiles]
		groups.append({
			'verb': row['verb'],
			'post': post,
			'actors': actors,
			'others': len(row['actor_ids']) - len(actors),
			'total': len(row['actor_ids']),
			'latest': row['latest'],
			'unread': row['unread'] > 0,
		})
	return groups, next_before
