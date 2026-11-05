from django.db.models.signals import post_save
from django.contrib.auth import get_user_model
from django.dispatch import receiver
from .models import Profile

User = get_user_model()

# raw=True — запись идёт из loaddata (например, при переносе базы на PostgreSQL).
# Тогда профиль приезжает из того же дампа: если создать его здесь, загрузка упадёт
# на дубле профиля, а save_profile — на отсутствующем профиле.

@receiver(post_save, sender=User)
def create_profile(sender, instance, created, raw=False, **kwargs):
	if created and not raw:
		Profile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_profile(sender, instance, raw=False, **kwargs):
	if not raw:
		instance.profile.save()
