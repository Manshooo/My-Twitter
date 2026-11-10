from django.contrib import messages
from django.db.models import Exists, OuterRef
from django.db.models.base import Model as Model
from django.shortcuts import HttpResponse, redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic.detail import DetailView
from django.views.generic.edit import UpdateView

from azzb.htmx import htmx_errors, htmx_login_required, is_htmx
from azzb.ratelimit import rate_limit
from post.models import Image, Like, Post
from post.pagination import PAGE_TEMPLATE, cursor_page, is_load_more, page_url

from . import relations
from .forms import UpdateUserForm
from .models import Block, FollowRequest, FollowThrough, Mute, Profile, Theme

THEME_COOKIE_AGE = 365 * 24 * 60 * 60


def remember_theme(response, theme):
	"""Cookie с темой: по ней сервер сразу отдаёт страницу в нужной теме — и гостям, и на этом
	устройстве после выхода. «Как в системе» — cookie убираем."""
	if theme:
		response.set_cookie('theme', theme, max_age=THEME_COOKIE_AGE, samesite='Lax')
	else:
		response.delete_cookie('theme', samesite='Lax')
	return response


@require_POST
@htmx_login_required
def set_theme(request):
	"""Переключатель темы: сохраняет выбор в аккаунте (C1). Гостям хватает cookie, её ставит azzb.js."""
	theme = request.POST.get('theme', '')
	if theme not in Theme.values:
		return htmx_errors('Неизвестная тема.')
	if request.user.theme != theme:
		request.user.theme = theme
		request.user.save(update_fields=['theme'])
	response = HttpResponse(status=204) if is_htmx(request) else redirect('index')
	return remember_theme(response, theme)


class ChangeProfileView(UpdateView):
	model = Profile
	form_class = UpdateUserForm
	template_name = 'accounts/profile_edit.html'
	
	def get_object(self, queryset=None) -> Model:
		return self.request.user.profile
	def get_form_kwargs(self):
		kwargs = super().get_form_kwargs()
		kwargs['instance'] = self.request.user  # Передаем текущего пользователя в качестве instance для формы
		return kwargs
	def get_success_url(self):
		return reverse_lazy('profile', kwargs={'slug': self.request.user})

	def form_valid(self, form):
		return remember_theme(super().form_valid(form), form.cleaned_data['theme'])

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		form = context['form']
		profile = self.request.user.profile
		context['media_fields'] = [
			('avatar', form['avatar'], form['avatar_clear'], profile.has_custom_avatar),
			('banner', form['banner'], form['banner_clear'], bool(profile.banner)),
		]
		return context

PROFILE_TABS = ('posts', 'replies', 'media', 'likes', 'following', 'followers')

# Что можно сделать с чужим профилем POST-запросом на его страницу (имя кнопки → действие).
PROFILE_ACTIONS = {
	'subscribe': relations.follow,
	'unsubscribe': relations.unfollow,
	'block': relations.block,
	'unblock': relations.unblock,
	'mute': relations.mute,
	'unmute': relations.unmute,
	'cancel_request': relations.cancel_request,
	# Убрать подписчика может только хозяин профиля: viewer — я, profile — подписчик.
	'remove_follower': relations.remove_follower,
}
PROFILE_TOASTS = {
	'block': '@{username} заблокирован(а)',
	'unblock': '@{username} разблокирован(а)',
	'mute': 'Посты @{username} больше не появятся в ваших лентах',
	'unmute': 'Посты @{username} снова в ваших лентах',
	'cancel_request': 'Заявка @{username} отозвана',
	'remove_follower': '@{username} больше не подписан(а) на вас',
}

# Подписка, блокировка и прочее — POST на страницу профиля, с лимитом частоты (E2).
@method_decorator(rate_limit('follow', '30/m', '300/h'), name='post')
class UserProfileDetailView(DetailView):
	template_name = "accounts/profile.html"
	model = Profile
	context_object_name = "profile"
	pk_url_kwarg = "username"
	slug_field = "user__username"

	def get_queryset(self):
		# Удалённый аккаунт пропадает сразу, хотя данные ещё хранятся (azzb/retention.py);
		# аккаунта с неподтверждённой почтой для других как будто ещё нет (Profile.objects.public).
		return Profile.objects.public().select_related("user")

	def get_template_names(self):
		return [PAGE_TEMPLATE] if is_load_more(self.request) else [self.template_name]

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		profile = self.object
		viewer = self.request.user.profile
		is_own = viewer.pk == profile.pk
		is_subscribed = FollowThrough.objects.filter(follower=viewer, followee=profile).exists()
		# Закрытый аккаунт (E5): посты, лайки и списки подписок — только подписчикам.
		can_see = is_own or not profile.is_private or is_subscribed
		# Лайки видит владелец всегда, остальные — только если он включил это в настройках.
		likes_visible = can_see and (is_own or profile.likes_public)

		tab = self.request.GET.get("tab", "posts")
		if tab not in PROFILE_TABS:
			tab = "posts"

		posts = Post.objects.for_feed(self.request.user)
		people = None
		if not can_see:
			items = posts.none()
		elif tab == "posts":
			items = posts.filter(author=profile).top_level()
		elif tab == "replies":
			items = posts.filter(author=profile, is_reply=True)
		elif tab == "media":
			items = posts.filter(author=profile).filter(Exists(Image.objects.filter(post=OuterRef("pk"))))
		elif tab == "likes" and likes_visible:
			liked_by_profile = Like.objects.filter(post_id=OuterRef("pk"), profile_id=profile.pk)
			items = posts.filter(Exists(liked_by_profile))
		else:
			items = posts.none()
			if tab in ("following", "followers"):
				related = profile.follows if tab == "following" else profile.followed_by
				people = related.public().select_related("user").order_by("username")

		page, cursor = cursor_page(items, self.request.GET.get("cursor"))

		context.update({
			"tab": tab,
			"is_own": is_own,
			"likes_visible": likes_visible,
			"posts": page,
			"next_url": page_url(self.request, cursor=cursor) if cursor else None,
			"people": people,
			# Считаем тех же, кого показывают списки, — без удалённых и отключённых аккаунтов.
			"following_count": profile.follows.public().count(),
			"followers_count": profile.followed_by.public().count(),
			"is_subscribed": is_subscribed,
			"can_see": can_see,
			"request_sent": not is_own and FollowRequest.objects.filter(requester=viewer, target=profile).exists(),
			"pending_requests": FollowRequest.objects.filter(target=profile).count() if is_own and profile.is_private else 0,
			# E3: блокировки и заглушение — для меню «⋯» и заглушки вместо постов.
			"i_blocked": not is_own and Block.objects.filter(blocker=viewer, blocked=profile).exists(),
			"blocked_me": not is_own and Block.objects.filter(blocker=profile, blocked=viewer).exists(),
			"i_muted": not is_own and Mute.objects.filter(muter=viewer, muted=profile).exists(),
		})
		return context

	def post(self, request, *args, **kwargs):
		profile = self.get_object()
		current_user_profile = request.user.profile

		# С собой ничего не делаем: подписку на себя запрещает CheckConstraint (раньше здесь был 500).
		# Подписка при блокировке в любую сторону не создаётся — это проверяет relations.follow.
		if profile.pk != current_user_profile.pk:
			action = next((name for name in PROFILE_ACTIONS if name in request.POST), None)
			if action:
				result = PROFILE_ACTIONS[action](current_user_profile, profile)
				toast = PROFILE_TOASTS.get(action)
				if result == relations.REQUESTED:
					toast = 'Заявка отправлена. @{username} увидит её и решит.'
				if toast:
					messages.success(request, toast.format(username=profile.user.username))

		next_url = request.POST.get('next')
		if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
			return redirect(next_url)
		return redirect('profile', slug=profile.user.username)


@require_POST
def answer_follow_request(request, username):
	"""Одобрить или отклонить заявку на подписку (E5)."""
	me = request.user.profile
	requester = Profile.objects.filter(user__username=username).first()
	if requester is not None:
		if 'approve' in request.POST and relations.approve_request(me, requester):
			messages.success(request, f'@{username} теперь читает вас')
		elif 'decline' in request.POST:
			relations.decline_request(me, requester)
	return redirect('follow-requests')


def follow_requests(request):
	"""Настройки → «Заявки на подписку» (E5)."""
	me = request.user.profile
	return render(request, 'accounts/follow_requests.html', {
		'requests': (
			FollowRequest.objects.filter(target=me, requester__in=Profile.objects.public())
			.select_related('requester__user').order_by('-created_at')
		),
	})


def blocked_accounts(request):
	"""Настройки → «Блокировки и заглушённые» (E3): кого я заблокировал и заглушил, с кнопкой «вернуть»."""
	me = request.user.profile
	return render(request, 'accounts/blocked.html', {
		'blocked': Profile.objects.filter(blocked_by_set__blocker=me).select_related('user').order_by('-blocked_by_set__created_at'),
		'muted': Profile.objects.filter(muted_by_set__muter=me).select_related('user').order_by('-muted_by_set__created_at'),
	})
