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

	username = forms.CharField(
		label=("Логин"),
		max_length=100,
		required=True,
		widget=forms.TextInput,
	)
	email =  forms.EmailField(
		label=_("Email"),
		required=True,
		widget=forms.EmailInput(),
	)
	
	class Meta:
		model = CustomUser
		fields = ['username', 'email']

class UpdateProfileForm():

	username = forms.CharField(
		label=("Отображаемое имя пользователя"),
		max_length=50,
		widget=forms.TextInput()
	)