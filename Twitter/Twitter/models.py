from datetime import datetime

from django.utils import timezone
from django.db import models
from django.contrib.auth.models import User


class Profile(models.Model):

	user = models.OneToOneField(User, on_delete=models.CASCADE)
	avatar = models.ImageField(default='default.jpg', upload_to='profile_images')
	bio = models.TextField()

	def __str__(self):
		return self.user.username
	
class Post(models.Model):
	
	post_text = models.TextField("Post text", blank=True, default="")
	post_author = models.ForeignKey(User, on_delete=models.CASCADE)
	post_date = models.DateTimeField("Date published")
	post_images = models.ImageField()
	
	def __str__(self):
		return f"{self.id, self.post_author}"
	
	class Meta():
		ordering = ["-id"]

class Tag(models.Model):

	name = models.CharField("Тег", unique=True, default=None, max_length=50)
	posts = models.ManyToManyField(Post, blank=True)

class Test(models.Model):

	test_field_Image = models.ImageField()
	test_field_File = models.FileField()