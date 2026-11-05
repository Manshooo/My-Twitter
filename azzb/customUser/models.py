from django.core import validators
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _
from django.db.models import F, Q
from django.core.exceptions import ValidationError


from uuid import uuid4

def user_profile_avatar_path(instance, filename):
	# файл загрузится в MEDIA_ROOT/users/user_<id>/<filename>
	return f"users/user_{instance.user.id}/{filename}"

# Профиль создаётся сигналом в customUser/signals.py.

USERNAME_MAX_LENGTH = 30

@deconstructible
class UsernameValidator(validators.RegexValidator):
	# Логин попадает в адрес профиля (/users/<логин>/), поэтому только безопасные для URL символы.
	regex = r"^[a-zA-Z0-9_.-]+\Z"
	message = _(
		"Введите верное имя пользователя. Доступны латинские буквы, цифры и символы _ . -"
	)
	flags = 0
class CustomUser(AbstractUser):
	username_validator = UsernameValidator()
	username = models.CharField(
		_("username"),
		# Колонку не сужаем: у старых аккаунтов логин может быть длиннее. Лимит 30 — валидатором.
		max_length=150,
		unique=True,
		help_text=_(
			"До 30 символов: латинские буквы, цифры и _ . -"
		),
		validators=[username_validator, validators.MaxLengthValidator(USERNAME_MAX_LENGTH)],
		error_messages={
			"unique": _("A user with that username already exists."),
		},
	)
	last_visit = models.DateTimeField("Последний раз в сети", default=None, null=True)

class FollowThrough(models.Model):
	follower = models.ForeignKey('Profile', on_delete=models.CASCADE, related_name='following_set')
	followee = models.ForeignKey('Profile', on_delete=models.CASCADE, related_name='followee_set')

	def clean(self):
		if self.follower_id == self.followee_id:
			raise ValidationError('Can not follow self.')

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=['follower', 'followee'], name='follow_once'),
			models.CheckConstraint(check=~Q(follower=F('followee')), name='not_follow_self')
		]

class Profile(models.Model):

	id = models.BigAutoField(primary_key=True)
	user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name="profile")
	username = models.CharField("Отображаемое имя пользователя", max_length=150, default=None, blank=True)
	avatar = models.ImageField(default='default/default_user_avatar.jpg', upload_to=user_profile_avatar_path)
	bio = models.CharField("О себе", max_length=250, blank=True, default="")
	# Галочка «подтверждённый аккаунт» ставится вручную в админке; значок staff — отдельно, по user.is_staff.
	is_verified = models.BooleanField("Подтверждённый аккаунт", default=False)
	likes_public = models.BooleanField("Показывать лайки всем", default=False)
	follows = models.ManyToManyField(
		"self",
		verbose_name="Подписчики",
		related_name="followed_by",
		symmetrical=False,
		blank=True,
		through=FollowThrough,
		through_fields=('follower', 'followee'),
	)
	
	def __str__(self):
		return self.username

	@property
	def has_custom_avatar(self):
		return bool(self.avatar) and self.avatar.name != self._meta.get_field('avatar').default

	@property
	def avatar_tone(self):
		# Цвет буквенного аватара из 5 пар токенов --avN-bg/--avN-ink, стабильный для пользователя.
		return (self.user_id or 0) % 5 + 1

	@property
	def initial(self):
		name = (self.username or self.user.username or '?').strip()
		return name[:1].upper() or '?'

	def save(self,  *args, **kwargs):
		if not self.username:
			self.username = self.user.username
		super(Profile, self).save(*args, **kwargs)
