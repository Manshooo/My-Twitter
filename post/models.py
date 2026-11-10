from django.db import connection, models
from django.utils import timezone
from django.db.models import BooleanField, Count, Exists, IntegerField, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from uuid import uuid4
from customUser.models import Block, Mute, Profile


class PostQuerySet(models.QuerySet):
	def visible_to(self, user):
		"""Единственное место, которое решает, какие посты может видеть пользователь.

		Все ленты, профиль, лайки, уведомления (а позже поиск) берут посты только отсюда.
		Скрываем удалённые, посты отключённых и забаненных аккаунтов (E4), скрытые модераторами
		(кроме собственных — автор видит их с пометкой) и тех, с кем у пользователя блокировка
		в любую сторону (E3). Репост виден, только если виден и сам исходный пост (D4).
		Сюда же лягут закрытые аккаунты (E5).
		"""
		posts = self._visible(user)
		originals = Post.objects.all()._visible(user).values('pk')
		return posts.filter(Q(is_repost=False) | Q(repost_of__in=originals))

	def _visible(self, user):
		posts = (
			self.filter(deleted_at__isnull=True, author__user__is_active=True)
			.exclude(author__user__banned_until__gt=timezone.now())
		)
		if user is None or not user.is_authenticated:
			return posts.filter(hidden_at__isnull=True)
		posts = posts.filter(Q(hidden_at__isnull=True) | Q(author_id=user.pk))
		# author_id — это id пользователя (to_field='user'), поэтому сравниваем с user_id профилей.
		return posts.exclude(
			author_id__in=Block.objects.filter(blocker__user_id=user.pk).values('blocked__user_id'),
		).exclude(
			author_id__in=Block.objects.filter(blocked__user_id=user.pk).values('blocker__user_id'),
		)

	def without_muted(self, user):
		"""Для лент: без постов заглушённых (E3). Профиль и ветка обсуждения их по-прежнему показывают."""
		if user is None or not user.is_authenticated:
			return self
		muted = Mute.objects.filter(muter__user_id=user.pk).values('muted__user_id')
		return self.exclude(author_id__in=muted).exclude(repost_of__author_id__in=muted)

	def top_level(self):
		"""Без ответов: ленты показывают только начала обсуждений, ответы живут на странице поста."""
		return self.filter(is_reply=False)

	def _cards(self, user):
		"""Всё, что нужно карточке: автор, картинки, число лайков, «мой ли лайк», «мой ли репост»
		и цитируемый пост — запросами на страницу, а не на каждый пост. Счётчики ответов
		и репостов хранятся в самом посте.

		Карточка репоста показывает исходный пост, поэтому лайки и прочее считаются по shown_id."""
		if user is not None and user.is_authenticated:
			liked = Exists(Like.objects.filter(post_id=OuterRef('shown_id'), profile_id=user.profile.pk))
			reposted = Exists(Post.objects.filter(
				repost_of_id=OuterRef('shown_id'), author_id=user.pk, deleted_at__isnull=True,
			))
			bookmarked = Exists(Bookmark.objects.filter(post_id=OuterRef('shown_id'), profile_id=user.profile.pk))
		else:
			liked = reposted = bookmarked = Value(False, output_field=BooleanField())
		likes = (
			Like.objects.filter(post_id=OuterRef('shown_id')).order_by()
			.values('post_id').annotate(n=Count('*')).values('n')
		)
		return (
			self.select_related(
				'author__user', 'reply_to__author__user', 'quote_of__author__user',
				'repost_of__author__user', 'repost_of__reply_to__author__user', 'repost_of__quote_of__author__user',
			)
			.prefetch_related('images', 'quote_of__images', 'repost_of__images', 'repost_of__quote_of__images')
			.annotate(shown_id=Coalesce('repost_of_id', 'id'), shown_quote_id=Coalesce('repost_of__quote_of_id', 'quote_of_id'))
			.annotate(
				likes_n=Coalesce(Subquery(likes, output_field=IntegerField()), 0),
				is_liked=liked,
				is_reposted=reposted,
				is_bookmarked=bookmarked,
				quote_available=Exists(Post.objects.visible_to(user).filter(pk=OuterRef('shown_quote_id'))),
			)
		)

	def for_feed(self, user):
		"""Посты, которые пользователь видит, готовые к выводу карточками."""
		return self.visible_to(user)._cards(user)

	def in_thread(self, user):
		"""Посты для ветки обсуждения: и те, что пользователь не видит, — они выводятся заглушкой
		(available=False), чтобы ветка не рвалась, а счётчик ответов сходился с тем, что в ней.
		Удалённый пост без ответов не нужен и заглушкой: он и в счётчиках не учитывается."""
		available = Exists(Post.objects.visible_to(user).filter(pk=OuterRef('pk')))
		return (
			self.exclude(deleted_at__isnull=False, replies_count=0)
			._cards(user).annotate(available=available)
		)


class Post(models.Model):
	
	id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
	text = models.TextField("Текст поста", blank=True, default="")
	author = models.ForeignKey(Profile, to_field='user', on_delete=models.CASCADE, related_name='posts')
	updated = models.DateTimeField("Дата обновления", auto_now=True)
	created_at = models.DateTimeField("Дата публикации", auto_now_add=True)
	likes = models.ManyToManyField(Profile, verbose_name="Классы", blank=True, related_name='profile_liked', through='Like')
	# Ответ — это обычный пост с родителем: лайки, картинки, а позже жалобы, поиск и уведомления
	# работают для ответов без отдельного кода. Посты удаляются мягко (deleted_at), так что ветка
	# не рвётся. Если строку всё же сотрут из базы (админка), ответ останется с reply_to = NULL,
	# а is_reply не даст ему всплыть в лентах как новому посту.
	reply_to = models.ForeignKey(
		'self', verbose_name="Ответ на", null=True, blank=True, on_delete=models.SET_NULL, related_name='replies',
	)
	is_reply = models.BooleanField("Это ответ", default=False)
	# Репост (D4) — пустой пост со ссылкой на исходный; в ленте выводится карточкой исходного.
	# is_repost, как is_reply, переживает стирание исходного из базы (repost_of = NULL).
	repost_of = models.ForeignKey(
		'self', verbose_name="Репост", null=True, blank=True, on_delete=models.SET_NULL, related_name='reposts',
	)
	is_repost = models.BooleanField("Это репост", default=False)
	# Цитата — обычный пост со своим текстом и карточкой цитируемого внутри.
	quote_of = models.ForeignKey(
		'self', verbose_name="Цитата", null=True, blank=True, on_delete=models.SET_NULL, related_name='quotes',
	)
	# Репосты и цитаты этого поста, кроме удалённых. Меняется только через shift_repost_counts.
	reposts_count = models.PositiveIntegerField("Репостов и цитат", default=0)
	# Когда автор последний раз менял текст. updated не годится: он меняется при любом save().
	edited_at = models.DateTimeField("Изменён", null=True, blank=True)
	# Скрыт модератором (E4): пропадает у всех, кроме автора, — тот видит пометку с причиной.
	hidden_at = models.DateTimeField("Скрыт модератором", null=True, blank=True)
	hidden_reason = models.CharField("Причина скрытия", max_length=200, blank=True, default="")
	# Сколько ответов во всей ветке под постом, на любой глубине, кроме удалённых авторами.
	# Меняется только через shift_ancestor_counts: при ответе и удалении — у всей цепочки вверх.
	replies_count = models.PositiveIntegerField("Ответов в ветке", default=0)
	# Удалён автором. Содержимое хранится ещё RETENTION_CONTENT (149-ФЗ, ст. 10.1) для запросов
	# госорганов, затем стирается (purged_at); строка остаётся, чтобы ветка не рвалась.
	deleted_at = models.DateTimeField("Удалён автором", null=True, blank=True)
	purged_at = models.DateTimeField("Содержимое стёрто", null=True, blank=True)

	objects = PostQuerySet.as_manager()
	def get_likes(self):
		return self.likes.all()
	@property
	def likes_count(self):
		return self.likes.all().count()
	def __str__(self) -> str:
		return str(self.author.username)
	class Meta():
		ordering = ["-created_at"]
		indexes = [
			# Ленты: только посты верхнего уровня, от новых к старым.
			models.Index(fields=['is_reply', '-created_at'], name='post_top_level_recent'),
			# Ветка: ответы на пост по времени.
			models.Index(fields=['reply_to', 'created_at'], name='post_replies_by_time'),
		]
		constraints = [
			models.UniqueConstraint(
				fields=['author', 'repost_of'], condition=Q(repost_of__isnull=False, deleted_at__isnull=True),
				name='repost_once',
			),
		]

def shift_ancestor_counts(post_ids, delta):
	"""Прибавить delta к replies_count всех постов выше по ветке — для каждого из post_ids.
	Один запрос на любое число постов: у предка, над которым удаляют сразу несколько
	постов (удаление аккаунта), счётчик уменьшится на их число."""
	post_ids = list(post_ids)
	if not post_ids:
		return
	marks = ', '.join(['%s'] * len(post_ids))
	# GREATEST — страховка: счётчик не уйдёт в минус, даже если когда-то разошёлся с базой.
	sql = f'''
		WITH RECURSIVE up(id) AS (
			SELECT reply_to_id FROM post_post WHERE id IN ({marks}) AND reply_to_id IS NOT NULL
			UNION ALL
			SELECT p.reply_to_id FROM post_post p JOIN up ON p.id = up.id WHERE p.reply_to_id IS NOT NULL
		)
		UPDATE post_post SET replies_count = GREATEST(replies_count + %s * c.n, 0)
		FROM (SELECT id, COUNT(*) AS n FROM up GROUP BY id) c
		WHERE post_post.id = c.id
	'''
	with connection.cursor() as cursor:
		cursor.execute(sql, [*post_ids, delta])


def shift_repost_counts(post_ids, delta):
	"""Прибавить delta к reposts_count постов, которые репостят или цитируют посты из post_ids."""
	post_ids = list(post_ids)
	if not post_ids:
		return
	marks = ', '.join(['%s'] * len(post_ids))
	sql = f'''
		UPDATE post_post SET reposts_count = GREATEST(reposts_count + %s * c.n, 0)
		FROM (
			SELECT COALESCE(repost_of_id, quote_of_id) AS id, COUNT(*) AS n FROM post_post
			WHERE id IN ({marks}) AND COALESCE(repost_of_id, quote_of_id) IS NOT NULL GROUP BY 1
		) c
		WHERE post_post.id = c.id
	'''
	with connection.cursor() as cursor:
		cursor.execute(sql, [delta, *post_ids])


class PostRevision(models.Model):
	"""Прежняя версия текста поста. Пишется при каждом редактировании; видна в админке —
	модераторам важно, что было в посте до правки (например, после жалобы)."""
	post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='revisions', verbose_name='Пост')
	text = models.TextField("Текст")
	# С какого момента этот текст был в посте и когда его заменили.
	valid_from = models.DateTimeField("Действовал с")
	replaced_at = models.DateTimeField("Заменён", auto_now_add=True)

	class Meta:
		ordering = ['-replaced_at']
		verbose_name = 'Прежняя версия'
		verbose_name_plural = 'Прежние версии'

	def __str__(self):
		return f'{self.post_id} до {self.replaced_at:%d.%m.%Y %H:%M}'


class Like(models.Model):
	"""Лайк с временем: нужен для «Горячего» с учётом свежести и для рекомендаций.

	Живёт в той же таблице, что и прежняя автоматическая связь Post.likes, поэтому
	post.likes.add()/remove() и все старые запросы работают как раньше.
	"""
	post = models.ForeignKey(Post, on_delete=models.CASCADE)
	profile = models.ForeignKey(Profile, on_delete=models.CASCADE)
	created_at = models.DateTimeField("Когда поставлен", auto_now_add=True)

	class Meta:
		db_table = 'post_post_likes'
		# Совпадает с уникальным индексом, который Django создал для автоматической связи.
		unique_together = [('post', 'profile')]
		verbose_name = 'Лайк'
		verbose_name_plural = 'Лайки'

	def __str__(self):
		return f'{self.profile} → {self.post_id}'


class Bookmark(models.Model):
	"""Закладка (D5): видна только владельцу, автор поста о ней не узнаёт."""
	profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='bookmarks')
	post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='bookmarks')
	created_at = models.DateTimeField("Когда добавлена", auto_now_add=True)

	class Meta:
		verbose_name = 'Закладка'
		verbose_name_plural = 'Закладки'
		constraints = [models.UniqueConstraint(fields=['profile', 'post'], name='bookmark_once')]
		indexes = [models.Index(fields=['profile', '-created_at'], name='bookmark_recent')]

	def __str__(self):
		return f'{self.profile} 🔖 {self.post_id}'


def post_image_path(instance, filename):
	# Файлы раскладываются по месяцам, чтобы в одной папке не копились сотни тысяч.
	return f"posts/{timezone.now():%Y/%m}/{filename}"


MAX_IMAGES = 4
ALT_MAX_LENGTH = 1000


class Image(models.Model):
	"""Картинка поста. Файл всегда WebP, перекодированный в post/media.py."""

	id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
	file = models.ImageField("Изображение", upload_to=post_image_path, default=None, null=True)
	post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='images', verbose_name="Пост")
	alt = models.CharField("Описание для незрячих", max_length=ALT_MAX_LENGTH, blank=True, default="")
	position = models.PositiveSmallIntegerField("Порядок", default=0)
	width = models.PositiveIntegerField("Ширина", null=True, blank=True)
	height = models.PositiveIntegerField("Высота", null=True, blank=True)

	class Meta:
		ordering = ['position']
		verbose_name = 'Картинка'
		verbose_name_plural = 'Картинки'

	@property
	def ratio(self):
		"""Пропорции одиночной картинки в ленте: как есть, но не уже 4:5 и не шире 2:1."""
		if not self.width or not self.height:
			return '16 / 9'
		value = min(max(self.width / self.height, 0.8), 2.0)
		return f'{value:.4f}'
