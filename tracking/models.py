"""Поведенческие данные для ленты «Для вас» (docs/data-collection.md).

Impression и InteractionEvent — секционированные по месяцам таблицы PostgreSQL (tracking/partitions.py):
старый месяц удаляется целиком, без долгого DELETE. В базе первичный ключ — (id, created_at):
секционирование требует ключ секции в ключе; Django о составном ключе не знает, ему хватает id.
Внешних ключей в базе нет (db_constraint=False): запись идёт на каждый показ, а события
пользователя стираются явно (tracking.services.erase_user_events).
"""
from django.conf import settings
from django.db import models
from django.utils import timezone


class Surface(models.TextChoices):
	FOR_YOU = 'for_you', 'Для вас'
	FOLLOWING = 'following', 'Подписки'
	HOT = 'hot', 'Горячее'
	LATEST = 'latest', 'Свежее'
	PROFILE = 'profile', 'Профиль'
	THREAD = 'thread', 'Пост и ответы'
	TAG = 'tag', 'Тег'
	SEARCH = 'search', 'Поиск'
	NOTIFICATIONS = 'notifications', 'Уведомления'
	BOOKMARKS = 'bookmarks', 'Закладки'
	OTHER = 'other', 'Другое'


class Device(models.TextChoices):
	PHONE = 'phone', 'Телефон'
	DESKTOP = 'desktop', 'Компьютер'


def _user():
	return models.ForeignKey(settings.AUTH_USER_MODEL, models.DO_NOTHING, db_constraint=False, related_name='+')


class Impression(models.Model):
	"""Показ поста (виден на ≥50% не меньше секунды) и время на экране. Хранится 30–60 дней."""

	class Kind(models.TextChoices):
		IMPRESSION = 'impression', 'Показ'
		DWELL = 'dwell', 'Время на экране'

	created_at = models.DateTimeField(default=timezone.now)
	user = _user()
	post = models.ForeignKey('post.Post', models.DO_NOTHING, db_constraint=False, related_name='+')
	kind = models.CharField(max_length=10, choices=Kind.choices)
	surface = models.CharField(max_length=16, choices=Surface.choices)
	position = models.PositiveSmallIntegerField(null=True)
	# Порция ленты, в которой пост показан: повторный показ в той же порции не считается.
	feed = models.UUIDField(null=True)
	seconds = models.PositiveSmallIntegerField(null=True)
	device = models.CharField(max_length=8, choices=Device.choices)

	class Meta:
		verbose_name = 'Показ'
		verbose_name_plural = 'Показы'


class InteractionEvent(models.Model):
	"""Всё, кроме показов: открытия, переходы, «Не интересно», снятые лайки и подписки, поиск.
	Хранится до 180 дней."""

	class Kind(models.TextChoices):
		OPEN = 'open', 'Открыт пост'
		EXPAND = 'expand', 'Раскрыт текст'
		MEDIA_OPEN = 'media_open', 'Открыта картинка'
		PROFILE_CLICK = 'profile_click', 'Переход в профиль'
		TAG_CLICK = 'tag_click', 'Переход по тегу'
		LINK_CLICK = 'link_click', 'Переход по ссылке'
		NOT_INTERESTED = 'not_interested', 'Не интересно'
		UNLIKE = 'unlike', 'Снят лайк'
		UNFOLLOW = 'unfollow', 'Отписка'
		SEARCH = 'search', 'Поиск'
		SEARCH_CLICK = 'search_click', 'Клик в поиске'

	created_at = models.DateTimeField(default=timezone.now)
	user = _user()
	kind = models.CharField(max_length=16, choices=Kind.choices)
	surface = models.CharField(max_length=16, choices=Surface.choices, default=Surface.OTHER)
	device = models.CharField(max_length=8, choices=Device.choices)
	post = models.ForeignKey('post.Post', models.DO_NOTHING, db_constraint=False, null=True, related_name='+')
	# Автор или профиль, о котором событие (переход в профиль, отписка, «Не интересно: автор»).
	target = models.ForeignKey(
		settings.AUTH_USER_MODEL, models.DO_NOTHING, db_constraint=False, null=True, related_name='+',
	)
	# Остальное по типу: тег, домен ссылки (без пути), номер картинки, запрос, вкладка, число результатов, позиция.
	data = models.JSONField(default=dict)

	class Meta:
		verbose_name = 'Событие'
		verbose_name_plural = 'События'


class NegativeFeedback(models.Model):
	"""«Не интересно»: что больше не показывать в «Свежем», «Горячем» и «Для вас».
	Живёт, пока существует аккаунт или пока человек сам не уберёт отметку."""

	class Kind(models.TextChoices):
		POST = 'post', 'Пост'
		AUTHOR = 'author', 'Автор'
		TAG = 'tag', 'Тема'

	created_at = models.DateTimeField(auto_now_add=True)
	user = models.ForeignKey(settings.AUTH_USER_MODEL, models.CASCADE, related_name='negative_feedback')
	kind = models.CharField(max_length=8, choices=Kind.choices)
	post = models.ForeignKey('post.Post', models.CASCADE, null=True, blank=True, related_name='+')
	# Как у Post.author — по user: author_id сравнивается с post.author_id без join.
	author = models.ForeignKey('customUser.Profile', models.CASCADE, to_field='user', null=True, blank=True, related_name='+')
	tag = models.ForeignKey('post.Hashtag', models.CASCADE, null=True, blank=True, related_name='+')

	class Meta:
		verbose_name = '«Не интересно»'
		verbose_name_plural = '«Не интересно»'
		ordering = ['-created_at']
		constraints = [
			models.UniqueConstraint(fields=['user', 'post'], condition=models.Q(kind='post'), name='negative_post_once'),
			models.UniqueConstraint(fields=['user', 'author'], condition=models.Q(kind='author'), name='negative_author_once'),
			models.UniqueConstraint(fields=['user', 'tag'], condition=models.Q(kind='tag'), name='negative_tag_once'),
			models.CheckConstraint(
				condition=(
					models.Q(kind='post', post__isnull=False, author__isnull=True, tag__isnull=True)
					| models.Q(kind='author', post__isnull=True, author__isnull=False, tag__isnull=True)
					| models.Q(kind='tag', post__isnull=True, author__isnull=True, tag__isnull=False)
				),
				name='negative_one_target',
			),
		]
