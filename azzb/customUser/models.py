from django.contrib.auth.validators import ASCIIUsernameValidator
from django.core import validators
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _

@deconstructible
class UsernameValidator(validators.RegexValidator):
	regex = r"^[a-zA-Z.@+-]+\Z"
	message = _(
		"Введите верное имя пользователя. Доступны только символы a-z, A-Z, ., @, +, -."
	)
	flags = 0
class CustomUser(AbstractUser):
	username_validator = UsernameValidator()
	username = models.CharField(
		_("username"),
		max_length=150,
		unique=True,
		help_text=_(
			"Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only."
		),
		validators=[username_validator],
		error_messages={
			"unique": _("A user with that username already exists."),
		},
	)