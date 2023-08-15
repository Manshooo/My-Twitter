import datetime

from django.utils import timezone
from django.db import models
from django.contrib.auth.models import User

class Post(models.Model):

	post_text = models.TextField()
	post_author = models.ForeignKey(User, on_delete=models.CASCADE)
	post_date = models.DateTimeField("date published")