from django.contrib.auth import authenticate, login
from django.shortcuts import HttpResponseRedirect, render, HttpResponse
from django.urls import reverse_lazy
from django.views.generic.edit import CreateView
from .forms import CustomUserCreationForm


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