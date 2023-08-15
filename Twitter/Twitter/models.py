import datetime

from django.utils import timezone
from django.db import models
from django.contrib.auth.models import User

class Post(models.Model):
	
	post_thumbs = models.CharField(max_length=255, blank=True, default="/")
	post_text = models.TextField(blank=True, default="")
	post_author = models.ForeignKey(User, on_delete=models.CASCADE)
	post_date = models.DateTimeField("date published")