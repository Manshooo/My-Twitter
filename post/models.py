from django.db import models
from django.utils import timezone
from django.db.models import BooleanField, Count, Exists, IntegerField, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from uuid import uuid4
from azzb.models import Profile


class PostQuerySet(models.QuerySet):
	def visible_to(self, user):
		"""Единственное место, которое решает, какие посты может видеть пользователь.

		Все ленты, профиль, лайки (а позже поиск и уведомления) берут посты только отсюда.
		Сейчас скрываем посты отключённых аккаунтов (is_active=False — это и есть бан).
		Сюда же лягут блокировки (E3), закрытые аккаунты (E5) и скрытие модераторами (E4).
		"""
		return self.filter(author__user__is_active=True)

	def top_level(self):
		"""Без ответов: ленты показывают только начала обсуждений, ответы живут на странице поста."""
		return self.filter(is_reply=False)

	def for_feed(self, user):
		"""Посты, готовые к выводу карточками: автор, картинки, число лайков и ответов,
		«мой ли лайк» и на что это ответ — одним запросом на страницу, без запросов на каждый пост."""
		if user is not None and user.is_authenticated:
			liked = Exists(Like.objects.filter(post_id=OuterRef('pk'), profile_id=user.profile.pk))
		else:
			liked = Value(False, output_field=BooleanField())
		# Считаем только ответы, которые пользователь и так увидит в ветке.
		replies = (
			self.model.objects.visible_to(user).filter(reply_to=OuterRef('pk'))
			.order_by().values('reply_to').annotate(n=Count('pk')).values('n')
		)
		return (
			self.visible_to(user)
			.select_related('author__user', 'reply_to__author__user')
			.prefetch_related('images')
			.annotate(
				likes_n=Count('likes', distinct=True),
				is_liked=liked,
				replies_n=Coalesce(Subquery(replies, output_field=IntegerField()), 0),
			)
		)


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
