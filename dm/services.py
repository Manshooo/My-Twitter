"""Правила и действия личных сообщений (F2). Вьюхи и сокет ходят только сюда."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Exists, F, OuterRef, Q, Subquery
from django.utils import timezone

from accounts.models import Block, DmPolicy, FollowThrough, Profile
from azzb.realtime import push
from post.media import process_post_image

from .models import MAX_IMAGES, MESSAGE_MAX_LENGTH, Conversation, Member, Message, MessageImage

PAGE_SIZE = 30
INBOX_SIZE = 30


def _pair(a, b):
	return (a, b) if a.pk < b.pk else (b, a)


def find_member(profile, peer):
	"""Моя сторона диалога с peer или None, если диалога ещё нет."""
	return (
		Member.objects.filter(profile=profile, peer=peer)
		.select_related('conversation', 'peer__user')
		.first()
	)


@transaction.atomic
def _open_conversation(sender, recipient):
	low, high = _pair(sender, recipient)
	conversation, created = Conversation.objects.get_or_create(low=low, high=high)
	if created:
		Member.objects.bulk_create([
			Member(conversation=conversation, profile=sender, peer=recipient),
			Member(conversation=conversation, profile=recipient, peer=sender),
		])
	return find_member(sender, recipient)


def refusal(sender, recipient, conversation=None):
	"""Почему sender не может написать recipient; None — может. Текст — для человека."""
	name = recipient.user.username
	if sender.pk == recipient.pk:
		return 'Себе написать нельзя.'
	if not Profile.objects.public().filter(pk=recipient.pk).exists():
		return 'Аккаунт удалён.'
	if recipient.user.is_banned:
		return f'Сейчас @{name} нельзя написать.'
	if Block.objects.filter(blocker=sender, blocked=recipient).exists():
		return f'Вы заблокировали @{name}. Разблокируйте, чтобы написать.'
	if Block.objects.filter(blocker=recipient, blocked=sender).exists():
		return f'Сейчас @{name} нельзя написать.'
	if recipient.dm_policy == DmPolicy.EVERYONE:
		return None
	# Настройка ограничивает только начало разговора: тому, кому человек писал сам, можно ответить.
	if conversation is not None and Message.objects.filter(conversation=conversation, sender=recipient).exists():
		return None
	if recipient.dm_policy == DmPolicy.FOLLOWING:
		if FollowThrough.objects.filter(follower=recipient, followee=sender).exists():
			return None
		return f'@{name} принимает сообщения только от тех, на кого подписан(а).'
	return f'@{name} не принимает новые сообщения.'


def clean_message_input(text, uploads):
	"""(текст, [обработанные картинки]) или ValidationError со списком сообщений."""
	text = (text or '').strip()
	uploads = list(uploads or [])
	errors = []
	if len(text) > MESSAGE_MAX_LENGTH:
		errors.append(f'Сообщение длиннее {MESSAGE_MAX_LENGTH} символов.')
	if len(uploads) > MAX_IMAGES:
		errors.append(f'К сообщению можно прикрепить не больше {MAX_IMAGES} картинок.')
	if not text and not uploads:
		errors.append('Напишите что-нибудь или прикрепите картинку.')
	if errors:
		raise ValidationError(errors)
	images = []
	for upload in uploads:
		try:
			images.append(process_post_image(upload))
		except ValidationError as error:
			errors.extend(error.messages)
	if errors:
		raise ValidationError(errors)
	return text, images


def send_message(sender, recipient, text='', uploads=(), member=None):
	"""Отправить сообщение; диалог заводится при первом. Возвращает (member отправителя, сообщение).
	ValidationError — нельзя писать или сообщение неверное."""
	reason = refusal(sender, recipient, member.conversation if member else None)
	if reason:
		raise ValidationError(reason)
	text, images = clean_message_input(text, uploads)
	saved = []
	try:
		with transaction.atomic():
			member = member or _open_conversation(sender, recipient)
			conversation = member.conversation
			message = Message.objects.create(conversation=conversation, sender=sender, text=text)
			for position, image in enumerate(images):
				row = MessageImage(message=message, position=position, width=image.width, height=image.height)
				row.file.save(image.content.name, image.content, save=False)
				saved.append(row.file)
				row.save()
			Conversation.objects.filter(pk=conversation.pk).update(last_message_at=message.created_at)
			# Своё сообщение — прочитанное. Диалог, удалённый получателем у себя, снова появится в его списке (_after_clear).
			Member.objects.filter(pk=member.pk).update(last_read_at=message.created_at)
			push([recipient.user_id, sender.user_id], 'dm', conversation=conversation.pk)
	except Exception:
		for file in saved:
			file.storage.delete(file.name)
		raise
	return member, message


def _unread():
	"""Есть ли у стороны диалога непрочитанные входящие (подзапрос для Member)."""
	return Exists(Message.objects.filter(
		conversation=OuterRef('conversation'),
		sender=OuterRef('peer'),
		created_at__gt=OuterRef('last_read_at'),
	))


def _after_clear():
	"""Диалог не удалён у себя или после удаления пришло новое."""
	return Q(cleared_at__isnull=True) | Q(conversation__last_message_at__gt=F('cleared_at'))


def inbox(profile, before=None, size=INBOX_SIZE):
	"""Диалоги, новые сверху, с последним сообщением и пометкой «есть непрочитанные».
	Возвращает (диалоги, before для следующей страницы)."""
	last = Message.objects.filter(conversation=OuterRef('conversation')).order_by('-id')
	members = (
		Member.objects.filter(profile=profile, conversation__last_message_at__isnull=False)
		.filter(_after_clear())
		.select_related('conversation', 'peer__user')
		.annotate(
			has_unread=_unread(),
			last_id=Subquery(last.values('id')[:1]),
		)
		.order_by('-conversation__last_message_at', '-pk')
	)
	if before is not None:
		members = members.filter(conversation__last_message_at__lt=before)
	members = list(members[:size + 1])
	next_before = members[size - 1].conversation.last_message_at if len(members) > size else None
	members = members[:size]
	previews = Message.objects.prefetch_related('images').in_bulk([member.last_id for member in members])
	for member in members:
		member.last_message = previews.get(member.last_id)
	return members, next_before


def unread_count(profile):
	"""Сколько диалогов с непрочитанными — число на значке «Сообщения»."""
	return (
		Member.objects.filter(profile=profile, conversation__last_message_at__isnull=False)
		.filter(_after_clear(), _unread())
		.count()
	)


def get_member(profile, conversation_id):
	return (
		Member.objects.filter(profile=profile, conversation_id=conversation_id)
		.select_related('conversation', 'peer__user')
		.first()
	)


def visible_messages(member):
	messages = Message.objects.filter(conversation_id=member.conversation_id).prefetch_related('images')
	if member.cleared_at:
		messages = messages.filter(created_at__gt=member.cleared_at)
	return messages


def page(member, before=None, size=PAGE_SIZE):
	"""Последние сообщения (до before), по возрастанию. Возвращает (сообщения, есть ли раньше)."""
	messages = visible_messages(member)
	if before is not None:
		messages = messages.filter(pk__lt=before)
	rows = list(messages.order_by('-pk')[:size + 1])
	return rows[:size][::-1], len(rows) > size


def newer(member, after, limit=100):
	return list(visible_messages(member).filter(pk__gt=after).order_by('pk')[:limit])


def mark_read(member):
	"""Прочитано всё, что пришло до сейчас. Собеседник увидит «Прочитано», мои вкладки — новый счётчик.
	True — что-то было непрочитано."""
	updated = Member.objects.filter(pk=member.pk).filter(_unread()).update(last_read_at=timezone.now())
	if updated:
		push([member.peer.user_id], 'dm-read', conversation=member.conversation_id)
		push([member.profile.user_id], 'badges')
	return bool(updated)


def seen_by_peer(member, messages):
	"""Последнее сообщение переписки, если оно моё и собеседник его прочитал (иначе None)."""
	last = messages[-1] if messages else None
	if last is None or last.sender_id != member.profile_id or last.deleted_at:
		return None
	peer_read = Member.objects.filter(conversation_id=member.conversation_id, profile_id=member.peer_id).values_list(
		'last_read_at', flat=True,
	).first()
	return last if peer_read and last.created_at <= peer_read else None


def delete_message(member, message_id):
	"""Удалить своё сообщение у обоих. Содержимое хранится до срока (azzb/retention.py)."""
	updated = Message.objects.filter(
		pk=message_id, conversation_id=member.conversation_id, sender=member.profile, deleted_at__isnull=True,
	).update(deleted_at=timezone.now())
	if updated:
		push([member.peer.user_id, member.profile.user_id], 'dm', conversation=member.conversation_id, deleted=int(message_id))
	return bool(updated)


def clear_conversation(member):
	"""«Удалить диалог»: у меня пропадает вся переписка до этого момента, у собеседника — нет."""
	now = timezone.now()
	Member.objects.filter(pk=member.pk).update(cleared_at=now, last_read_at=now)
	push([member.profile.user_id], 'badges')


def purge_messages(messages):
	"""Стереть содержимое: текст и картинки (файлы удалит сигнал). Строка остаётся заглушкой."""
	with transaction.atomic():
		ids = list(messages.filter(purged_at__isnull=True).values_list('pk', flat=True))
		if not ids:
			return 0
		MessageImage.objects.filter(message_id__in=ids).delete()
		now = timezone.now()
		Message.objects.filter(pk__in=ids, deleted_at__isnull=True).update(deleted_at=now)
		Message.objects.filter(pk__in=ids).update(text='', purged_at=now)
	return len(ids)
