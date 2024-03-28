from django import forms
from django.contrib.auth.forms import PasswordChangeForm, UserCreationForm
from django.core.validators import validate_email
from django.utils.translation import gettext_lazy as _

from .models import CustomUser

class CustomUserCreationForm(UserCreationForm):
	email = forms.EmailField(
		label=_("Email"),
		widget=forms.EmailInput(),
		help_text=validate_email.message
	)

	class Meta:
		model = CustomUser
		fields = ('username', 'email', 'password1', 'password2')
class UpdateUserForm(forms.ModelForm):
	class Meta:
		model = CustomUser
		fields = ['email', 'first_name', 'last_name']

	username = forms.CharField(
		label=("Отображаемое имя"),
		max_length=100,
		required=True,
		widget=forms.TextInput,
	)
	email =  forms.EmailField(
		label=_("Email"),
		required=True,
		widget=forms.EmailInput(),
	)
	first_name = forms.CharField(
		label=("Имя"),
		max_length=50,
		required=False,
		widget=forms.TextInput
	)
	last_name = forms.CharField(
		label=("Фамилия"),
		max_length=50,
		required=False,
		widget=forms.TextInput
	)
	bio = forms.CharField(
		label=("О себе"),
		max_length=250,
		required=False,
		widget=forms.Textarea
	)

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		if 'instance' in kwargs:
			instance = kwargs['instance']
			if hasattr(instance, 'profile'):
				self.fields['bio'].initial = instance.profile.bio
				self.fields['username'].initial = instance.profile.username

	def save(self, commit=True):
		user = super().save(commit=False)
		if commit:
			user.save()
			if hasattr(user, 'profile'):
				profile = user.profile
				profile.bio = self.cleaned_data['bio']
				profile.username = self.cleaned_data['username']
				profile.save()
		return user
