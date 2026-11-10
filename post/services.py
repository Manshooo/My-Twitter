"""Создание, правка, удаление постов и лайки. Одна точка и для страниц (HTMX), и для API."""
import uuid

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .media import process_post_image
from .models import ALT_MAX_LENGTH, MAX_IMAGES, Image, Like, Post, PostRevision, shift_ancestor_counts
from .serializer import POST_MAX_LENGTH


def clean_post_input(text, uploads, alts):
	"""Проверка текста и картинок. Возвращает (текст, [(картинка, alt)]) или бросает ValidationError
	со списком понятных пользователю сообщений."""
	text = (text or '').strip()
	uploads = list(uploads or [])
	alts = list(alts or [])
	errors = []
	if len(text) > POST_MAX_LENGTH:
		errors.append(f'Пост длиннее {POST_MAX_LENGTH} символов.')
	if len(uploads) > MAX_IMAGES:
		errors.append(f'К посту можно прикрепить не больше {MAX_IMAGES} картинок.')
	if not text and not uploads:
		errors.append('Напишите что-нибудь или прикрепите картинку.')
	if errors:
		raise ValidationError(errors)

	processed = []
	for index, upload in enumerate(uploads):
		try:
			image = process_post_image(upload)
		except ValidationError as error:
			errors.extend(error.messages)
			continue
		alt = (alts[index] if index < len(alts) else '') or ''
		processed.append((image, alt.strip()[:ALT_MAX_LENGTH]))
	if errors:
		raise ValidationError(errors)
	return text, processed


def publish_post(author, text='', uploads=(), alts=(), reply_to=None):
	"""Новый пост или ответ (reply_to — пост, который автор ответа видит; проверяет вызывающий)."""
	text, images = clean_post_input(text, uploads, alts)
	saved = []
	try:
		with transaction.atomic():
			post = Post.objects.create(author=author, text=text, reply_to=reply_to, is_reply=reply_to is not None)
			if reply_to is not None:
				shift_ancestor_counts([post.pk], +1)
			for position, (image, alt) in enumerate(images):
				row = Image(post=post, alt=alt, position=position, width=image.width, height=image.height)
				row.file.save(image.content.name, image.content, save=False)
				saved.append(row.file)
				row.save()
	except Exception:
		# Запись в базу откатилась — файлы, уже записанные на диск, тоже не нужны.
		for file in saved:
			file.storage.delete(file.name)
		raise
	return post


def edit_post(post, text):
	"""Новый текст поста. Картинки не меняются. Прежний текст уходит в историю.
	Возвращает True, если текст правда изменился."""
	text = (text or '').strip()
	errors = []
	if len(text) > POST_MAX_LENGTH:
		errors.append(f'Пост длиннее {POST_MAX_LENGTH} символов.')
	if not text and not post.images.exists():
		errors.append('Пост без картинок не может быть пустым.')
	if errors:
		raise ValidationError(errors)
	with transaction.atomic():
		# Блокируем строку: две правки одновременно не должны потерять версию между ними.
		current = Post.objects.select_for_update().get(pk=post.pk)
		if text == current.text:
			return False
		PostRevision.objects.create(post=current, text=current.text, valid_from=current.edited_at or current.created_at)
		current.text = text
		current.edited_at = timezone.now()
		current.save(update_fields=['text', 'edited_at', 'updated'])
	post.text, post.edited_at = current.text, current.edited_at
	return True


def delete_posts(posts):
	"""Мягкое удаление: посты пропадают отовсюду, у веток над ними −1 в счётчиках ответов.
	Содержимое остаётся до purge_posts — его требует хранить 149-ФЗ (см. azzb/retention.py)."""
	with transaction.atomic():
		ids = list(posts.filter(deleted_at__isnull=True).select_for_update().values_list('pk', flat=True))
		if not ids:
			return 0
		Post.objects.filter(pk__in=ids).update(deleted_at=timezone.now())
		shift_ancestor_counts(ids, -1)
	return len(ids)


def delete_post(post):
	return delete_posts(Post.objects.filter(pk=post.pk))


def purge_posts(posts):
	"""Стереть содержимое удалённых постов: текст, картинки (файлы удалит сигнал), прежние
	версии, лайки. Строка остаётся пустой заглушкой, чтобы ветка не рвалась."""
	with transaction.atomic():
		ids = list(posts.filter(deleted_at__isnull=False, purged_at__isnull=True).values_list('pk', flat=True))
		if not ids:
			return 0
		Image.objects.filter(post_id__in=ids).delete()
		PostRevision.objects.filter(post_id__in=ids).delete()
		Like.objects.filter(post_id__in=ids).delete()
		Post.objects.filter(pk__in=ids).update(text='', purged_at=timezone.now())
	return len(ids)


def toggle_like(post, profile):
	"""Поставить или снять лайк. Возвращает (лайк стоит?, сколько лайков теперь)."""
	deleted, _ = Like.objects.filter(post=post, profile=profile).delete()
	if not deleted:
		# Двойной клик или два запроса разом: второй не должен упасть на уникальном индексе.
		Like.objects.get_or_create(post=post, profile=profile)
	return not deleted, Like.objects.filter(post=post).count()


def find_reply_target(user, raw_id):
	"""Пост, на который отвечают, по id из формы. None — это не ответ.
	ValidationError с code="invalid" (мусор вместо id) или "not_found" (поста нет или он не виден)."""
	if not raw_id:
		return None
	try:
		post_id = uuid.UUID(str(raw_id))
	except ValueError:
		raise ValidationError('Пост, на который вы отвечаете, не найден.', code='invalid')
	post = Post.objects.visible_to(user).filter(pk=post_id).first()
	if post is None:
		raise ValidationError('Пост, на который вы отвечаете, удалён или недоступен.', code='not_found')
	return post
