from django.db import models
from django.db.models import BooleanField, Count, Exists, OuterRef, Value
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

	def for_feed(self, user):
		"""Посты, готовые к выводу карточками: автор, картинки, число лайков и «мой ли лайк»
		одним запросом на страницу, без отдельного запроса на каждый пост."""
		if user is not None and user.is_authenticated:
			liked = Exists(Like.objects.filter(post_id=OuterRef('pk'), profile_id=user.profile.pk))
		else:
			liked = Value(False, output_field=BooleanField())
		return (
			self.visible_to(user)
			.select_related('author__user')
			.prefetch_related('images')
			.annotate(likes_n=Count('likes', distinct=True), is_liked=liked)
		)


class Post(models.Model):
	
	id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
	text = models.TextField("Текст поста", blank=True, default="")
	author = models.ForeignKey(Profile, to_field='user', on_delete=models.CASCADE, related_name='posts')
	updated = models.DateTimeField("Дата обновления", auto_now=True)
	created_at = models.DateTimeField("Дата публикации", auto_now_add=True)
	likes = models.ManyToManyField(Profile, verbose_name="Классы", blank=True, related_name='profile_liked', through='Like')

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


class Image(models.Model):
	
	id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
	file = models.ImageField("Изображение", upload_to='images', default=None ,null=True)

	post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='images', verbose_name="Имагес")