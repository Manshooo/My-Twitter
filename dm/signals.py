from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import MessageImage


@receiver(post_delete, sender=MessageImage)
def delete_image_file(sender, instance, **kwargs):
	"""Как у картинок постов: файл удаляется после коммита, чтобы откат не оставил запись без файла."""
	if instance.file:
		storage, name = instance.file.storage, instance.file.name
		transaction.on_commit(lambda: storage.delete(name))
