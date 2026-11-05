from django.contrib.auth import authenticate, login
from django.db.models.base import Model as Model
from django.shortcuts import redirect, render, HttpResponse
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView

from rest_framework.decorators import api_view

from django.db.models import Exists, OuterRef

from post.models import Image, Like, Post
from post.pagination import PAGE_TEMPLATE, cursor_page, is_load_more, page_url

from .forms import CustomUserCreationForm, UpdateUserForm
from .models import FollowThrough, Profile
from .serializers import *

class CustomSignUp(CreateView):
	form_class = CustomUserCreationForm
	success_url = reverse_lazy('login')
	template_name = 'registration/signup.html'

	def register(request):
		if request.method == 'POST':
			form = CustomUserCreationForm(request.POST)
			if form.is_valid():
				form.save()
				username = form.cleaned_data.get('username')
				password = form.cleaned_data.get('password2')
				user = authenticate(username=username, password=password)
				login(request, user)
			else:
				return HttpResponse(form.errors)
		else:
			form = CustomUserCreationForm()
		return render(request, 'registration/signup.html', {'form': form})

class ChangeProfileView(UpdateView):
	model = Profile
	form_class = UpdateUserForm
	template_name = 'registration/edit.html'
	
	def get_object(self, queryset=None) -> Model:
		return self.request.user.profile
	def get_form_kwargs(self):
		kwargs = super().get_form_kwargs()
		kwargs['instance'] = self.request.user  # Передаем текущего пользователя в качестве instance для формы
		return kwargs
	def get_success_url(self):
		return reverse_lazy('profile', kwargs={'slug': self.request.user})

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		form = context['form']
		profile = self.request.user.profile
		context['media_fields'] = [
			('avatar', form['avatar'], form['avatar_clear'], profile.has_custom_avatar),
			('banner', form['banner'], form['banner_clear'], bool(profile.banner)),
		]
		return context

PROFILE_TABS = ('posts', 'media', 'likes', 'following', 'followers')

class UserProfileDetailView(DetailView):
	template_name = "registration/profile.html"
	model = Profile
	context_object_name = "profile"
	pk_url_kwarg = "username"
	slug_field = "user__username"

	def get_queryset(self):
		return Profile.objects.select_related("user")

	def get_template_names(self):
		return [PAGE_TEMPLATE] if is_load_more(self.request) else [self.template_name]

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		profile = self.object
		viewer = self.request.user.profile
		is_own = viewer.pk == profile.pk
		# Лайки видит владелец всегда, остальные — только если он включил это в настройках.
		likes_visible = is_own or profile.likes_public

		tab = self.request.GET.get("tab", "posts")
		if tab not in PROFILE_TABS:
			tab = "posts"

		posts = Post.objects.for_feed(self.request.user)
		people = None
		if tab == "posts":
			items = posts.filter(author=profile)
		elif tab == "media":
			items = posts.filter(author=profile).filter(Exists(Image.objects.filter(post=OuterRef("pk"))))
		elif tab == "likes" and likes_visible:
			liked_by_profile = Like.objects.filter(post_id=OuterRef("pk"), profile_id=profile.pk)
			items = posts.filter(Exists(liked_by_profile))
		else:
			items = posts.none()
			if tab in ("following", "followers"):
				related = profile.follows if tab == "following" else profile.followed_by
				people = related.select_related("user").order_by("username")

		page, cursor = cursor_page(items, self.request.GET.get("cursor"))

		context.update({
			"tab": tab,
			"is_own": is_own,
			"likes_visible": likes_visible,
			"posts": page,
			"next_url": page_url(self.request, cursor=cursor) if cursor else None,
			"people": people,
			"following_count": profile.follows.count(),
			"followers_count": profile.followed_by.count(),
			"is_subscribed": FollowThrough.objects.filter(follower=viewer, followee=profile).exists(),
		})
		return context

	def post(self, request, *args, **kwargs):
		profile = self.get_object()
		current_user_profile = request.user.profile

		# На себя подписаться нельзя: это запрещает CheckConstraint, и раньше здесь падало с 500.
		if profile.pk != current_user_profile.pk:
			if 'subscribe' in request.POST:
				FollowThrough.objects.get_or_create(follower=current_user_profile, followee=profile)
			elif 'unsubscribe' in request.POST:
				FollowThrough.objects.filter(follower=current_user_profile, followee=profile).delete()

		next_url = request.POST.get('next')
		if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
			return redirect(next_url)
		return redirect('profile', slug=profile.user.username)
