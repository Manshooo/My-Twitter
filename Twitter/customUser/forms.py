from django import forms
from django.contrib.auth.forms import UserCreationForm
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
		fields = ('username',)