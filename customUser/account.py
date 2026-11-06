"""Настройки аккаунта (E6): выгрузка своих данных и удаление аккаунта (152-ФЗ)."""
import json
import tempfile
import zipfile
from pathlib import PurePosixPath

from django import forms
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.http import FileResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from azzb.ratelimit import rate_limit
from moderation.models import Ban, Report
from post.models import Like, Post

from .models import DEFAULT_AVATAR, Block, FollowThrough, Mute


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
	return render(request, 'registration/account.html', {'delete_form': DeleteAccountForm(request.user)})


def _media_name(field, folder):
	return str(PurePosixPath(folder) / PurePosixPath(field.name).name)


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
	for post in Post.objects.filter(author=profile).prefetch_related('images', 'revisions').order_by('created_at'):
		posts.append({
			'id': post.pk,
			'created_at': post.created_at,
			'edited_at': post.edited_at,
			'text': post.text,
			'reply_to': post.reply_to_id,
			'hidden_by_moderator': bool(post.hidden_at),
			'images': [{'file': attach(image.file, f'posts/{post.pk}'), 'alt': image.alt} for image in post.images.all()],
			'previous_versions': [
				{'text': revision.text, 'valid_from': revision.valid_from, 'replaced_at': revision.replaced_at}
				for revision in post.revisions.all()
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
			'is_verified': profile.is_verified,
			'avatar': attach(profile.avatar, 'profile'),
			'banner': attach(profile.banner, 'profile'),
		},
		'posts': posts,
		'likes': [
			{'post': like.post_id, 'at': like.created_at}
			for like in Like.objects.filter(profile=profile).order_by('created_at')
		],
		'following': people(FollowThrough.objects.filter(follower=profile).select_related('followee__user'), 'followee'),
		'followers': people(FollowThrough.objects.filter(followee=profile).select_related('follower__user'), 'follower'),
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
			'data.json — аккаунт, профиль, посты (с прежними версиями), лайки, подписки, блокировки, жалобы.\n'
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


@require_POST
@login_required
def delete_account(request):
	"""Удаляет аккаунт сразу и насовсем: профиль, посты с картинками, лайки, подписки.
	Файлы постов удаляет сигнал post_delete у Image, аватар и баннер — здесь."""
	user = request.user
	form = DeleteAccountForm(user, request.POST)
	if not form.is_valid():
		return render(request, 'registration/account.html', {'delete_form': form}, status=400)
	profile = user.profile
	media = [field for field in (profile.avatar, profile.banner) if field and field.name and field.name != DEFAULT_AVATAR]
	with transaction.atomic():
		for field in media:
			storage, name = field.storage, field.name
			transaction.on_commit(lambda storage=storage, name=name: storage.delete(name))
		logout(request)
		user.delete()
	messages.success(request, 'Аккаунт удалён. Спасибо, что были с нами.')
	return redirect('index')
