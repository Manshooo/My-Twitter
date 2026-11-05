"""Создание постов. Одна точка и для composer, и (позже) для ответов."""
from django.core.exceptions import ValidationError
from django.db import transaction

from .media import process_post_image
from .models import ALT_MAX_LENGTH, MAX_IMAGES, Image, Post
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


def publish_post(author, text='', uploads=(), alts=()):
	text, images = clean_post_input(text, uploads, alts)
	saved = []
	try:
		with transaction.atomic():
			post = Post.objects.create(author=author, text=text)
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
