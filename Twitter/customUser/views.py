from django.contrib.auth import authenticate, login
from django.shortcuts import HttpResponseRedirect, render
from django.urls import reverse_lazy
from django.views.generic.edit import CreateView
from .forms import CustomUserCreationForm


class CustomSignUp(CreateView):
	form_class = CustomUserCreationForm
	success_url = reverse_lazy('login')
	template_name = 'registration/signup.html'