from datetime import datetime
from typing import Iterable, Optional

from django.utils import timezone
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User


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
class Profile(models.Model):

	user = models.OneToOneField(User, on_delete=models.CASCADE)
	username = models.CharField("Отображаемое имя пользователя", max_length=150, default=None, blank=True)
	avatar = models.ImageField(default='default/default_user_avatar.jpg', upload_to=user_profile_avatar_path)
	bio = models.TextField(blank=True)
	follows = models.ManyToManyField("self", related_name="followed_by", symmetrical=False, blank=True)
	def __str__(self):
		return self.username
	def save(self,  *args, **kwargs):
		if not self.username:
			self.username = self.user
		super(Profile, self).save(*args, **kwargs)

class Post(models.Model):
	
	post_text = models.TextField("Post text", blank=True, default="")
	post_author = models.ForeignKey(Profile, on_delete=models.CASCADE)
	post_date = models.DateTimeField("Date published", blank=True)
	post_images = models.ImageField(blank=True)
	
	def save(self,  *args, **kwargs):
		if not self.post_date:
			self.post_date = datetime.now()
		super(Post, self).save(*args, **kwargs)
	
	class Meta():
		ordering = ["-post_date"]

class Tag(models.Model):

	name = models.CharField("Тег", unique=True, default=None, max_length=50)
	posts = models.ManyToManyField(Post, blank=True)

class Test(models.Model):

	test_field_Image = models.ImageField()
	test_field_File = models.FileField()