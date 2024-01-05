from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
import uuid
from django.conf import settings

from customUser.models import Profile

User = settings.AUTH_USER_MODEL



	