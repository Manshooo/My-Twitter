from django.core import validators
from django.db import models
from django.contrib.auth.models import AbstractUser, User
from django.db.models.signals import post_save
from django.dispatch.dispatcher import receiver
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _
from django.db.models import F, Q
from django.core.exceptions import ValidationError


from uuid import uuid4

def user_profile_avatar_path(instance, filename):
	# файл загрузится в MEDIA_ROOT/users/user_<id>/<filename>
	return f"users/user_{instance.user.id}/{filename}"
@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
	if created:
		user_profile = Profile(user=instance)
		user_profile.save()
		user_profile.follows.add(instance.profile)
		user_profile.save()

@deconstructible
class UsernameValidator(validators.RegexValidator):
	regex = r"^[a-zA-Z.@0-9+-]+\Z"
	message = _(
		"Введите верное имя пользователя. Доступные символы буквы a-Z, цифры 0-9, ./@/+/-."
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
	def save(self,  *args, **kwargs):
		if not self.username:
			self.username = self.user.username
		super(Profile, self).save(*args, **kwargs)
