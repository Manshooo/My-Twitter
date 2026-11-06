from django.db import connection, models
from django.utils import timezone
from django.db.models import BooleanField, Count, Exists, OuterRef, Q, Value
from django.db.models.query import ModelIterable
from uuid import uuid4
from customUser.models import Block, Mute, Profile


class PostQuerySet(models.QuerySet):
	# Для кого досчитать replies_n после загрузки постов (см. for_feed и _fetch_all): (user,) или None.
	_reply_counts_for = None

	def _clone(self):
		clone = super()._clone()
		clone._reply_counts_for = self._reply_counts_for
		return clone

	def _fetch_all(self):
		# Число ответов во всей ветке — рекурсивный запрос, его не выразить аннотацией. Считаем его
		# здесь, когда посты уже загружены: так страница ленты получает счётчики разом, двумя
		# запросами, а не по запросу на пост, и ни одна вьюха не забудет их досчитать.
		counting = self._result_cache is None and self._reply_counts_for is not None
		super()._fetch_all()
		if counting and self._iterable_class is ModelIterable and self._result_cache:
			counts = reply_counts(self._result_cache, self._reply_counts_for[0])
			for post in self._result_cache:
				post.replies_n = counts[post.pk]

	def visible_to(self, user):
		"""Единственное место, которое решает, какие посты может видеть пользователь.

		Все ленты, профиль, лайки (а позже поиск и уведомления) берут посты только отсюда.
		Скрываем посты отключённых и забаненных аккаунтов (E4), скрытые модераторами (кроме
		собственных — автор видит их с пометкой) и тех, с кем у пользователя блокировка в
		любую сторону (E3). Сюда же лягут закрытые аккаунты (E5).
		"""
		posts = self.filter(author__user__is_active=True).exclude(author__user__banned_until__gt=timezone.now())
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
		return self.exclude(author_id__in=Mute.objects.filter(muter__user_id=user.pk).values('muted__user_id'))

	def top_level(self):
		"""Без ответов: ленты показывают только начала обсуждений, ответы живут на странице поста."""
		return self.filter(is_reply=False)

	def for_feed(self, user):
		"""Посты, готовые к выводу карточками: автор, картинки, число лайков и ответов,
		«мой ли лайк» и на что это ответ — запросами на страницу, а не на каждый пост.
		Число ответов (replies_n) досчитывается после загрузки, см. _fetch_all."""
		if user is not None and user.is_authenticated:
			liked = Exists(Like.objects.filter(post_id=OuterRef('pk'), profile_id=user.profile.pk))
		else:
			liked = Value(False, output_field=BooleanField())
		posts = (
			self.visible_to(user)
			.select_related('author__user', 'reply_to__author__user')
			.prefetch_related('images')
			.annotate(likes_n=Count('likes', distinct=True), is_liked=liked)
		)
		posts._reply_counts_for = (user,)
		return posts


class Post(models.Model):
	
	id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
	text = models.TextField("Текст поста", blank=True, default="")
	author = models.ForeignKey(Profile, to_field='user', on_delete=models.CASCADE, related_name='posts')
	updated = models.DateTimeField("Дата обновления", auto_now=True)
	created_at = models.DateTimeField("Дата публикации", auto_now_add=True)
	likes = models.ManyToManyField(Profile, verbose_name="Классы", blank=True, related_name='profile_liked', through='Like')
	# Ответ — это обычный пост с родителем: лайки, картинки, а позже жалобы, поиск и уведомления
	# работают для ответов без отдельного кода. Если родителя удалят, ответ останется
	# (reply_to станет NULL), а is_reply не даст ему всплыть в лентах как новому посту.
	reply_to = models.ForeignKey(
		'self', verbose_name="Ответ на", null=True, blank=True, on_delete=models.SET_NULL, related_name='replies',
	)
	is_reply = models.BooleanField("Это ответ", default=False)
	# Когда автор последний раз менял текст. updated не годится: он меняется при любом save().
	edited_at = models.DateTimeField("Изменён", null=True, blank=True)
	# Скрыт модератором (E4): пропадает у всех, кроме автора, — тот видит пометку с причиной.
	hidden_at = models.DateTimeField("Скрыт модератором", null=True, blank=True)
	hidden_reason = models.CharField("Причина скрытия", max_length=200, blank=True, default="")

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

def reply_counts(posts, user):
	"""{id поста: сколько ответов во всей его ветке} — с ответами на ответы на любой глубине.

	Считаются только ответы, до которых пользователь дойдёт по ветке: если ответ ему не виден
	(автор заблокирован, забанен, ответ скрыт модератором), не считается и всё, что под ним.
	Два запроса на любое число постов: рекурсивный — все потомки, второй — какие из них видны.
	"""
	roots = [post.pk for post in posts]
	counts = dict.fromkeys(roots, 0)
	if not roots:
		return counts
	qn = connection.ops.quote_name
	table, pk, parent = qn(Post._meta.db_table), qn(Post._meta.pk.column), qn(Post._meta.get_field('reply_to').column)
	marks = ', '.join(['%s'] * len(roots))
	# UNION, а не UNION ALL: если на странице и ответ, и его родитель, ветка ответа
	# встретится дважды — повторы отбрасываем.
	sql = f'''
		WITH RECURSIVE tree(id, parent) AS (
			SELECT {pk}, {parent} FROM {table} WHERE {parent} IN ({marks})
			UNION
			SELECT p.{pk}, p.{parent} FROM {table} p JOIN tree ON p.{parent} = tree.id
		)
		SELECT id, parent FROM tree
	'''
	with connection.cursor() as cursor:
		cursor.execute(sql, roots)
		edges = cursor.fetchall()
	if not edges:
		return counts
	visible = set(Post.objects.visible_to(user).filter(pk__in=[child for child, _ in edges]).values_list('pk', flat=True))
	children = {}
	for child, parent_id in edges:
		if child in visible:
			children.setdefault(parent_id, []).append(child)
	# Размер поддерева — обходом «сначала дети» на своём стеке, без рекурсии Python: ветки
	# бывают длинными. Пост страницы может оказаться внутри ветки другого — тогда его размер
	# уже посчитан и берётся готовым.
	size = {}
	for root in roots:
		stack = [(root, False)]
		while stack:
			node, kids_done = stack.pop()
			if node in size:
				continue
			kids = children.get(node, ())
			if kids_done:
				size[node] = sum(1 + size[kid] for kid in kids)
			else:
				stack.append((node, True))
				stack.extend((kid, False) for kid in kids if kid not in size)
		counts[root] = size[root]
	return counts


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
