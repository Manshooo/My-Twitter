from django.contrib.auth import authenticate, login
from django.db.models.base import Model as Model
from django.shortcuts import redirect, render, HttpResponse
from django.urls import reverse_lazy
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView

from rest_framework.decorators import api_view

from post.models import Post

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

class UserProfileDetailView(DetailView):
	template_name = "registration/profile.html"
	model = Profile
	context_object_name = "profile"
	pk_url_kwarg = "username"
	slug_field = "user__username"

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		profile_user = self.get_object().user
		profile_posts = Post.objects.select_related("author").filter(author=self.get_object())
		if profile_posts:
			context["profile_posts"] = profile_posts
		context["is_subscribed"] = FollowThrough.objects.filter(follower=self.request.user.profile, followee=profile_user.profile).exists()
		return context

	def post(self, request, *args, **kwargs):
		profile_user = self.get_object().user
		current_user_profile = request.user.profile

		if 'subscribe' in request.POST:
			FollowThrough.objects.get_or_create(follower=current_user_profile, followee=profile_user.profile)

		elif 'unsubscribe' in request.POST:
			FollowThrough.objects.filter(follower=current_user_profile, followee=profile_user.profile).delete()

		return redirect('profile', slug=profile_user)