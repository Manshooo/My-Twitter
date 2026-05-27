import uuid

from customUser.models import Profile
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

User = settings.AUTH_USER_MODEL
