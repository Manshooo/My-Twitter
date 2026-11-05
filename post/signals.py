from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Image


@receiver(post_delete, sender=Image)
def delete_image_file(sender, instance, **kwargs):
	"""Удалили пост или картинку — удаляем и файл, иначе media/ копит мусор.

	Ждём коммита: если транзакция откатится, запись вернётся, и файл должен остаться.
	"""
	if instance.file:
		storage, name = instance.file.storage, instance.file.name
		transaction.on_commit(lambda: storage.delete(name))
