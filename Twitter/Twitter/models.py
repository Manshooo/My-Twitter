import datetime

from django.utils import timezone
from django.db import models
from django.contrib.auth.models import User

class Post(models.Model):
	
	post_text = models.TextField("Post text", blank=True, default="")
	post_author = models.ForeignKey(User, on_delete=models.CASCADE)
	post_date = models.DateTimeField("Date published")
	post_images = models.ImageField()

class Test(models.Model):

	test_field_Image = models.ImageField()
	test_field_File = models.FileField()