"""Создание, правка, удаление постов и лайки. Одна точка и для страниц (HTMX), и для API."""
import uuid
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import Profile
from notifications.models import Notification
from notifications.services import notify, retract

from .media import process_post_image
from .models import (
	ALT_MAX_LENGTH, MAX_IMAGES, POLL_DURATIONS, POLL_MAX_OPTIONS, POLL_MIN_OPTIONS, POLL_OPTION_MAX_LENGTH,
	Bookmark, Hashtag, Image, Like, Mention, Poll, PollOption, PollVote, Post, PostHashtag, PostRevision,
	shift_ancestor_counts, shift_repost_counts,
)
from .serializer import POST_MAX_LENGTH
from .text import hashtags, mentions


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


def original(post):
	"""Репост сам по себе не лайкают, не цитируют и не комментируют — всё это достаётся исходному."""
	return post.repost_of if post.is_repost and post.repost_of_id else post


def sync_entities(post):
	"""Теги и упоминания поста по его тексту — при публикации и после правки. Уведомление получает
	только новый упомянутый; кто уже получил «ответ» или «цитату» на этот пост, второе не получает."""
	names = hashtags(post.text)
	for name in names:
		Hashtag.objects.get_or_create(name=name)
	tags = Hashtag.objects.filter(name__in=names)
	PostHashtag.objects.filter(post=post).exclude(hashtag__in=tags).delete()
	PostHashtag.objects.bulk_create([PostHashtag(post=post, hashtag=tag) for tag in tags], ignore_conflicts=True)

	people = set(
		Profile.objects.filter(user__username__in=mentions(post.text), user__is_active=True)
		.exclude(pk=post.author.pk).values_list('pk', flat=True)
	)
	gone = Mention.objects.filter(post=post).exclude(profile_id__in=people)
	Notification.objects.filter(
		verb=Notification.Verb.MENTION, post=post, recipient_id__in=gone.values('profile_id'),
	).delete()
	gone.delete()
	known = set(Mention.objects.filter(post=post).values_list('profile_id', flat=True))
	already = {author.user_id for author in (
		post.reply_to.author if post.reply_to_id else None, post.quote_of.author if post.quote_of_id else None,
	) if author}
	for profile in Profile.objects.filter(pk__in=people - known):
		Mention.objects.create(post=post, profile=profile)
		if profile.user_id not in already:
			notify(profile, post.author, Notification.Verb.MENTION, post)


def clean_poll(options, duration, text, has_images):
	"""Варианты и срок опроса из формы. None — опроса нет. ValidationError — понятные сообщения."""
	options = [option.strip() for option in options or [] if option and option.strip()]
	if not options:
		return None
	errors = []
	if not POLL_MIN_OPTIONS <= len(options) <= POLL_MAX_OPTIONS:
		errors.append(f'В опросе от {POLL_MIN_OPTIONS} до {POLL_MAX_OPTIONS} вариантов.')
	if any(len(option) > POLL_OPTION_MAX_LENGTH for option in options):
		errors.append(f'Вариант ответа — не длиннее {POLL_OPTION_MAX_LENGTH} символов.')
	if len({option.casefold() for option in options}) != len(options):
		errors.append('Варианты ответа не должны повторяться.')
	if not (text or '').strip():
		errors.append('Напишите вопрос опроса.')
	if has_images:
		errors.append('К опросу нельзя прикрепить картинки.')
	try:
		hours = int(duration)
	except (TypeError, ValueError):
		hours = None
	if hours not in POLL_DURATIONS:
		errors.append('Выберите срок опроса.')
	if errors:
		raise ValidationError(errors)
	return options, hours


def vote(post, profile, option_id):
	"""Голос в опросе поста. Один на человека, только пока опрос идёт, автор не голосует.
	ValidationError с понятным сообщением, если нельзя."""
	poll = getattr(post, 'poll', None)
	if poll is None:
		raise ValidationError('В посте нет опроса.')
	if post.author_id == profile.user_id:
		raise ValidationError('В своём опросе голосовать нельзя.')
	if not poll.is_open:
		raise ValidationError('Опрос уже закончился.')
	option = poll.options.filter(pk=option_id).first() if str(option_id).isdigit() else None
	if option is None:
		raise ValidationError('Такого варианта нет.')
	_, created = PollVote.objects.get_or_create(poll=poll, profile=profile, defaults={'option': option})
	if not created:
		raise ValidationError('Вы уже проголосовали.')


def publish_post(author, text='', uploads=(), alts=(), reply_to=None, quote_of=None, poll_options=(), poll_duration=None):
	"""Новый пост, ответ или цитата, по желанию — с опросом. reply_to и quote_of — посты,
	которые автор видит (проверяет вызывающий, см. find_post_target)."""
	poll = clean_poll(poll_options, poll_duration, text, bool(uploads))
	text, images = clean_post_input(text, uploads, alts)
	saved = []
	try:
		with transaction.atomic():
			post = Post.objects.create(
				author=author, text=text, reply_to=reply_to, is_reply=reply_to is not None, quote_of=quote_of,
			)
			if reply_to is not None:
				shift_ancestor_counts([post.pk], +1)
				notify(reply_to.author, author, Notification.Verb.REPLY, post)
			if quote_of is not None:
				shift_repost_counts([post.pk], +1)
				notify(quote_of.author, author, Notification.Verb.QUOTE, post)
			sync_entities(post)
			if poll is not None:
				options, hours = poll
				created = Poll.objects.create(post=post, ends_at=timezone.now() + timedelta(hours=hours))
				PollOption.objects.bulk_create(
					[PollOption(poll=created, text=option, position=index) for index, option in enumerate(options)]
				)
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
		sync_entities(current)
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
		shift_repost_counts(ids, -1)
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
		Bookmark.objects.filter(post_id__in=ids).delete()
		PostHashtag.objects.filter(post_id__in=ids).delete()
		Mention.objects.filter(post_id__in=ids).delete()
		Poll.objects.filter(post_id__in=ids).delete()
		Post.objects.filter(pk__in=ids).update(text='', purged_at=timezone.now())
	return len(ids)


def toggle_like(post, profile):
	"""Поставить или снять лайк. Возвращает (лайк стоит?, сколько лайков теперь)."""
	deleted, _ = Like.objects.filter(post=post, profile=profile).delete()
	if deleted:
		retract(post.author, profile, Notification.Verb.LIKE, post)
	else:
		# Двойной клик или два запроса разом: второй не должен упасть на уникальном индексе.
		Like.objects.get_or_create(post=post, profile=profile)
		notify(post.author, profile, Notification.Verb.LIKE, post)
	return not deleted, Like.objects.filter(post=post).count()


def toggle_pin(post, profile):
	"""Закрепить свой пост в профиле или открепить. Закреплённый может быть один:
	новый заменяет прежний. Возвращает True, если пост теперь закреплён."""
	pinned = profile.pinned_post_id != post.pk
	profile.pinned_post = post if pinned else None
	profile.save(update_fields=['pinned_post'])
	return pinned


def toggle_bookmark(post, profile):
	"""Добавить в закладки или убрать. Возвращает True, если закладка есть."""
	deleted, _ = Bookmark.objects.filter(post=post, profile=profile).delete()
	if not deleted:
		Bookmark.objects.get_or_create(post=post, profile=profile)
	return not deleted


def toggle_repost(post, profile):
	"""Сделать или отменить репост (post — исходный). Возвращает (репост есть?, репостов и цитат теперь).
	Отмена — мягкое удаление строки репоста: факт передачи хранится, как у постов (149-ФЗ)."""
	with transaction.atomic():
		# Блокируем исходный: два быстрых нажатия не создадут двух репостов и не собьют счётчик.
		Post.objects.select_for_update().filter(pk=post.pk).first()
		existing = Post.objects.filter(author=profile, repost_of=post, deleted_at__isnull=True)
		if existing.exists():
			delete_posts(existing)
			retract(post.author, profile, Notification.Verb.REPOST, post)
			reposted = False
		else:
			repost = Post.objects.create(author=profile, repost_of=post, is_repost=True)
			shift_repost_counts([repost.pk], +1)
			notify(post.author, profile, Notification.Verb.REPOST, post)
			reposted = True
	return reposted, Post.objects.values_list('reposts_count', flat=True).get(pk=post.pk)


TARGET_TEXT = {
	'reply': ('Пост, на который вы отвечаете, не найден.', 'Пост, на который вы отвечаете, удалён или недоступен.'),
	'quote': ('Цитируемый пост не найден.', 'Цитируемый пост удалён или недоступен.'),
}


def find_post_target(user, raw_id, kind='reply'):
	"""Пост, на который отвечают или который цитируют, по id из формы. None — id не передан.
	Репост заменяется исходным постом. ValidationError с code="invalid" (мусор вместо id)
	или "not_found" (поста нет или он не виден)."""
	if not raw_id:
		return None
	invalid, missing = TARGET_TEXT[kind]
	try:
		post_id = uuid.UUID(str(raw_id))
	except ValueError:
		raise ValidationError(invalid, code='invalid')
	post = Post.objects.visible_to(user).filter(pk=post_id).select_related('author', 'repost_of__author').first()
	post = post and original(post)
	# Ответить на свой скрытый пост автор может (он его видит), процитировать — нет: цитату увидят все.
	if post is None or (kind == 'quote' and post.hidden_at is not None):
		raise ValidationError(missing, code='not_found')
	# Пост закрытого аккаунта цитирует только сам автор: цитата вынесла бы его за круг подписчиков.
	if kind == 'quote' and post.author.is_private and post.author.user_id != user.pk:
		raise ValidationError('Пост из закрытого аккаунта нельзя цитировать.', code='forbidden')
	return post


def find_reply_target(user, raw_id):
	return find_post_target(user, raw_id, 'reply')
