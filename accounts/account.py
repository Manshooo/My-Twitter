"""Настройки аккаунта (E6): выгрузка своих данных и удаление аккаунта.

Удаление мягкое: удалённое хранится полгода на случай законных запросов госорганов
(azzb/retention.py). Стереть раньше по просьбе человека может модератор через админку."""
import json
import tempfile
import zipfile
from pathlib import PurePosixPath

from allauth.account.models import EmailAddress
from django import forms
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from azzb.activity import Action, record
from azzb.models import ActivityRecord
from azzb.ratelimit import rate_limit
from dm.models import Member, Message
from dm.services import purge_messages
from moderation.models import Ban, Report
from notifications.models import Notification
from post.models import Bookmark, Like, Mention, PollVote, Post
from post.services import delete_posts, purge_posts

from .models import DEFAULT_AVATAR, Block, FollowRequest, FollowThrough, Mute


class DeleteAccountForm(forms.Form):
	confirm = forms.CharField(label='Пароль', widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}))

	def __init__(self, user, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.user = user
		# Без пароля (например, вход через соцсеть в будущем) подтверждаем логином.
		if not user.has_usable_password():
			self.fields['confirm'] = forms.CharField(label=f'Введите логин {user.username}, чтобы подтвердить')

	def clean_confirm(self):
		value = self.cleaned_data['confirm']
		ok = self.user.check_password(value) if self.user.has_usable_password() else value.strip() == self.user.username
		if not ok:
			raise forms.ValidationError('Неверный пароль.' if self.user.has_usable_password() else 'Логин не совпадает.')
		return value


@login_required
def account_settings(request):
	return render(request, 'accounts/account_settings.html', {'delete_form': DeleteAccountForm(request.user)})


def _media_name(field, folder):
	return str(PurePosixPath(folder) / PurePosixPath(field.name).name)


def _poll(post):
	poll = getattr(post, 'poll', None)
	if poll is None:
		return None
	return {'ends_at': poll.ends_at, 'options': [option.text for option in poll.options.all()]}


def collect_user_data(user):
	"""Всё, что AzzB хранит о пользователе, — в виде словаря для data.json, плюс файлы для архива."""
	profile = user.profile
	files = []

	def attach(field, folder):
		if not field or not field.name or field.name == DEFAULT_AVATAR:
			return None
		name = _media_name(field, folder)
		files.append((name, field))
		return name

	posts = []
	own_posts = Post.objects.filter(author=profile, purged_at__isnull=True)
	for post in own_posts.select_related('poll').prefetch_related('images', 'revisions', 'poll__options').order_by('created_at'):
		posts.append({
			'id': post.pk,
			'created_at': post.created_at,
			'edited_at': post.edited_at,
			'deleted_at': post.deleted_at,
			'text': post.text,
			'reply_to': post.reply_to_id,
			'repost_of': post.repost_of_id,
			'quote_of': post.quote_of_id,
			'poll': _poll(post),
			'hidden_by_moderator': bool(post.hidden_at),
			'images': [{'file': attach(image.file, f'posts/{post.pk}'), 'alt': image.alt} for image in post.images.all()],
			'previous_versions': [
				{'text': revision.text, 'valid_from': revision.valid_from, 'replaced_at': revision.replaced_at}
				for revision in post.revisions.all()
			],
		})

	conversations = []
	for member in Member.objects.filter(profile=profile).select_related('peer__user').order_by('pk'):
		messages = Message.objects.filter(conversation_id=member.conversation_id, purged_at__isnull=True)
		conversations.append({
			'with': member.peer.user.username,
			'messages': [
				{
					'from': 'me' if message.sender_id == profile.pk else member.peer.user.username,
					'at': message.created_at,
					'deleted_at': message.deleted_at,
					'text': message.text,
					'images': [attach(image.file, f'messages/{member.conversation_id}') for image in message.images.all()],
				}
				for message in messages.prefetch_related('images').order_by('pk')
			],
		})

	def people(queryset, field):
		return [{'username': getattr(row, field).user.username, 'since': row.created_at} for row in queryset]

	return {
		'exported_at': timezone.now(),
		'account': {
			'username': user.username,
			'email': user.email,
			'first_name': user.first_name,
			'last_name': user.last_name,
			'date_joined': user.date_joined,
			'last_login': user.last_login,
			'last_visit': user.last_visit,
			'theme': user.theme,
			'terms_accepted_at': user.terms_accepted_at,
			'pd_consent_at': user.pd_consent_at,
		},
		'profile': {
			'display_name': profile.username,
			'bio': profile.bio,
			'likes_public': profile.likes_public,
			'is_private': profile.is_private,
			'search_indexing': profile.search_indexing,
			'is_verified': profile.is_verified,
			'avatar': attach(profile.avatar, 'profile'),
			'banner': attach(profile.banner, 'profile'),
		},
		'posts': posts,
		'likes': [
			{'post': like.post_id, 'at': like.created_at}
			for like in Like.objects.filter(profile=profile).order_by('created_at')
		],
		'poll_votes': [
			{'post': vote.poll.post_id, 'option': vote.option.text, 'at': vote.created_at}
			for vote in PollVote.objects.filter(profile=profile).select_related('poll', 'option')
		],
		'conversations': conversations,
		'bookmarks': [
			{'post': bookmark.post_id, 'at': bookmark.created_at}
			for bookmark in Bookmark.objects.filter(profile=profile).order_by('created_at')
		],
		'following': people(FollowThrough.objects.filter(follower=profile).select_related('followee__user'), 'followee'),
		'followers': people(FollowThrough.objects.filter(followee=profile).select_related('follower__user'), 'follower'),
		'follow_requests_sent': [
			{'username': row.target.user.username, 'since': row.created_at}
			for row in FollowRequest.objects.filter(requester=profile).select_related('target__user')
		],
		'follow_requests_received': [
			{'username': row.requester.user.username, 'since': row.created_at}
			for row in FollowRequest.objects.filter(target=profile).select_related('requester__user')
		],
		'blocked': people(Block.objects.filter(blocker=profile).select_related('blocked__user'), 'blocked'),
		'muted': people(Mute.objects.filter(muter=profile).select_related('muted__user'), 'muted'),
		'reports_made': [
			{'reason': report.get_reason_display(), 'comment': report.comment, 'post': report.post_id,
			 'profile': report.profile.user.username, 'status': report.get_status_display(), 'created_at': report.created_at}
			for report in Report.objects.filter(reporter=profile).select_related('profile__user')
		],
		'bans': [
			{'reason': ban.reason, 'until': ban.until, 'created_at': ban.created_at, 'lifted_at': ban.lifted_at}
			for ban in Ban.objects.filter(user=user)
		],
		'activity_log': [
			{'action': row.get_action_display(), 'at': row.created_at, 'ip': row.ip, 'browser': row.user_agent}
			for row in ActivityRecord.objects.filter(user=user)
		],
	}, files


@require_POST
@login_required
@rate_limit('export', '3/h', message='Архив можно скачивать не чаще трёх раз в час.')
def export_data(request):
	"""ZIP: data.json со всеми данными и папки с картинками профиля и постов."""
	data, files = collect_user_data(request.user)
	archive = tempfile.SpooledTemporaryFile(max_size=20 * 1024 * 1024)
	with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
		bundle.writestr('data.json', json.dumps(data, cls=DjangoJSONEncoder, ensure_ascii=False, indent=2))
		bundle.writestr('README.txt', (
			'Ваши данные из AzzB.\n\n'
			'data.json — аккаунт, профиль, посты (с прежними версиями и ещё не стёртыми удалёнными), лайки,\n'
			'подписки, блокировки, жалобы и журнал входов и публикаций.\n'
			'conversations в data.json — личные сообщения (ваши и собеседников), messages/ — картинки из них.\n'
			'profile/ и posts/ — загруженные вами картинки (в том виде, в каком они хранятся на сайте).\n'
		))
		for name, field in files:
			try:
				with field.storage.open(field.name, 'rb') as source:
					bundle.writestr(name, source.read())
			except FileNotFoundError:
				continue
	archive.seek(0)
	filename = f'azzb-{request.user.username}-{timezone.localdate():%Y-%m-%d}.zip'
	return FileResponse(archive, as_attachment=True, filename=filename, content_type='application/zip')


def erase_account(user):
	"""Стереть данные удалённого аккаунта: содержимое постов и сообщений, лайки, подписки, блокировки,
	почту, имя, «О себе», картинки профиля. Строка пользователя остаётся обезличенной
	(логин deleted-<id>), чтобы ветки обсуждений с его ответами не рвались, а логин освободился.
	Журнал действий не трогаем — он хранится год (azzb/retention.py)."""
	profile = user.profile
	media = [field for field in (profile.avatar, profile.banner) if field and field.name and field.name != DEFAULT_AVATAR]
	with transaction.atomic():
		posts = Post.objects.filter(author=profile)
		delete_posts(posts)
		purge_posts(posts)
		Like.objects.filter(profile=profile).delete()
		Bookmark.objects.filter(profile=profile).delete()
		Mention.objects.filter(profile=profile).delete()
		PollVote.objects.filter(profile=profile).delete()
		FollowThrough.objects.filter(Q(follower=profile) | Q(followee=profile)).delete()
		Block.objects.filter(Q(blocker=profile) | Q(blocked=profile)).delete()
		Mute.objects.filter(Q(muter=profile) | Q(muted=profile)).delete()
		FollowRequest.objects.filter(Q(requester=profile) | Q(target=profile)).delete()
		Notification.objects.filter(Q(recipient=profile) | Q(actor=profile)).delete()
		# Свои сообщения стираются у собеседников тоже; их диалоги остаются с «Удалённым аккаунтом».
		purge_messages(Message.objects.filter(sender=profile))
		Member.objects.filter(profile=profile).delete()
		EmailAddress.objects.filter(user=user).delete()
		for field in media:
			storage, name = field.storage, field.name
			transaction.on_commit(lambda storage=storage, name=name: storage.delete(name))
		now = timezone.now()
		user.username = f'deleted-{user.pk}'
		user.email = user.first_name = user.last_name = ''
		user.set_unusable_password()
		user.is_active = False
		user.deleted_at = user.deleted_at or now
		user.erased_at = now
		user.last_visit = None
		user.save()
		profile.username = 'Удалённый аккаунт'
		profile.bio = ''
		profile.avatar = DEFAULT_AVATAR
		profile.banner = ''
		profile.is_verified = profile.likes_public = profile.is_private = profile.search_indexing = False
		profile.save()


@require_POST
@login_required
def delete_account(request):
	"""Аккаунт отключается сразу: профиль и посты пропадают для всех, войти больше нельзя.
	Данные стираются через полгода командой purge_expired (azzb/retention.py)."""
	user = request.user
	form = DeleteAccountForm(user, request.POST)
	if not form.is_valid():
		return render(request, 'accounts/account_settings.html', {'delete_form': form}, status=400)
	with transaction.atomic():
		record(request, Action.ACCOUNT_DELETE)
		user.deleted_at = timezone.now()
		user.is_active = False
		user.save(update_fields=['deleted_at', 'is_active'])
		delete_posts(Post.objects.filter(author_id=user.pk))
		logout(request)
	messages.success(request, 'Аккаунт удалён. Спасибо, что были с нами.')
	return redirect('index')
