from typing import Any
from django import forms
from django.contrib.auth import get_user_model
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
	""" def __init__(self, *args: Any, **kwargs: Any) -> None:
		super().__init__(*args, **kwargs)
		self.fields['username'].widget.attrs.update({"placeholder": "Имя пользователя"})
		self.fields['email'].widget.attrs.update({"placeholder": "Электронная почта"})
		self.fields['username'].widget.attrs.update({"placeholder": "Пароль, минимиум 8 символов"}) """
	class Meta:
		model = CustomUser
		fields = ('username', 'email', 'password1', 'password2')