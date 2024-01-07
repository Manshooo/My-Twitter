from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.contrib.auth import authenticate, login
from django.shortcuts import render, HttpResponse
from django.urls import reverse_lazy
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView

from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework import status

from post.models import Post

from .forms import CustomUserCreationForm
from .models import Profile
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

class UserProfileDetailView(DetailView):
	template_name = "registration/profile.html"
	model = Profile
	context_object_name = "profile"
	pk_url_kwarg = "username"
	slug_field = "user__username"

	def	get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		profile_posts = Post.objects.select_related("author").filter(author=self.get_object())
		if profile_posts:
			context["profile_posts"] = profile_posts
		return context
