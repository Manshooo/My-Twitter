from django.db import models
from uuid import uuid4
from azzb.models import Profile

class Post(models.Model):
	
	id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
	text = models.TextField("Текст поста", blank=True, default="")
	author = models.ForeignKey(Profile, to_field='user', on_delete=models.CASCADE, related_name='posts')
	updated = models.DateTimeField("Дата обновления", auto_now=True)
	created_at = models.DateTimeField("Дата публикации", auto_now_add=True)
	likes = models.ManyToManyField(Profile, verbose_name="Классы", blank=True, related_name='profile_liked')

	def get_likes(self):
		return self.likes.all()
	@property
	def likes_count(self):
		return self.likes.all().count()
	def __str__(self) -> str:
		return str(self.author.username)
	class Meta():
		ordering = ["-created_at"]

class Image(models.Model):
	
	id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
	file = models.ImageField("Изображение", upload_to='images', default=None ,null=True)

	post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='images', verbose_name="Имагес")