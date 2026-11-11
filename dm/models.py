"""Личные сообщения (F2): диалоги двух людей.

Удаление сообщения мягкое, как у постов: текст и картинки стираются через RETENTION_CONTENT
(azzb/retention.py). Админки у этих моделей нет намеренно — переписку видят только участники."""
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from accounts.models import Profile

MESSAGE_MAX_LENGTH = 2000
MAX_IMAGES = 4


class Conversation(models.Model):
	"""Пара хранится упорядоченной (low.pk < high.pk): второго диалога с тем же человеком не бывает."""
	low = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='+')
	high = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='+')
	created_at = models.DateTimeField(auto_now_add=True)
	# Порядок списка диалогов; пусто — сообщений ещё нет.
	last_message_at = models.DateTimeField(null=True, blank=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=['low', 'high'], name='dm_pair_once'),
			models.CheckConstraint(condition=Q(low__lt=F('high')), name='dm_pair_ordered'),
		]


class Member(models.Model):
	"""Сторона диалога: что человек прочитал и что удалил у себя."""
	conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='members')
	profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='dm_memberships')
	# Собеседник — копия из Conversation, чтобы список диалогов строился без условий «low или high».
	peer = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='+')
	last_read_at = models.DateTimeField(default=timezone.now)
	# «Удалить диалог»: сообщения до этого момента человек больше не видит, у собеседника они остаются.
	cleared_at = models.DateTimeField(null=True, blank=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=['conversation', 'profile'], name='dm_member_once'),
			models.UniqueConstraint(fields=['profile', 'peer'], name='dm_member_pair_once'),
		]


class Message(models.Model):
	conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
	sender = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='+')
	text = models.TextField(blank=True, default='')
	created_at = models.DateTimeField(default=timezone.now)
	# Удалено отправителем: у обоих заглушка «Сообщение удалено».
	deleted_at = models.DateTimeField(null=True, blank=True)
	# Содержимое стёрто (срок хранения вышел или аккаунт отправителя стёрт).
	purged_at = models.DateTimeField(null=True, blank=True)

	class Meta:
		indexes = [models.Index(fields=['conversation', 'id'], name='dm_message_conv_id')]


def message_image_path(instance, filename):
	return f"dm/{timezone.now():%Y/%m}/{filename}"


class MessageImage(models.Model):
	"""Файл всегда WebP, перекодированный в post/media.py (без EXIF)."""
	message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='images')
	file = models.ImageField(upload_to=message_image_path)
	position = models.PositiveSmallIntegerField(default=0)
	width = models.PositiveIntegerField(null=True, blank=True)
	height = models.PositiveIntegerField(null=True, blank=True)

	class Meta:
		ordering = ['position']

	@property
	def ratio(self):
		from post.models import Image
		return Image.ratio.fget(self)
