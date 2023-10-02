from datetime import datetime
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()

def user_profile_avatar_path(instance, filename):
    # файл загрузится в MEDIA_ROOT/users/user_<id>/<filename>
	return f"users/user_{instance.user.id}/{filename}"
@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
	if created:
		user_profile = Profile(user=instance)
		user_profile.save()
		user_profile.follows.add(instance.profile)
		user_profile.save()
class Profile(models.Model):
	user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)
	username = models.CharField("Отображаемое имя пользователя", max_length=150, default=None, blank=True)
	avatar = models.ImageField(default='default/default_user_avatar.jpg', upload_to=user_profile_avatar_path)
	bio = models.CharField("О себе", max_length=250, blank=True, default="")
	follows = models.ManyToManyField("self", related_name="followed_by", symmetrical=False, blank=True)

	def has_posts(self):
		posts = Post.objects.filter(author=self.user.id)
		if posts:
			return True
	def __str__(self):
		return self.username
	def save(self,  *args, **kwargs):
		if not self.username:
			self.username = self.user.username
		super(Profile, self).save(*args, **kwargs)
	

class Post(models.Model):
	
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	text = models.TextField("Текст поста", blank=True, default="")
	author = models.ForeignKey(Profile, to_field='user', on_delete=models.CASCADE, related_name='post_author')
	updated = models.DateTimeField("Дата обновления", auto_now=True)
	created_at = models.DateTimeField("Дата публикации", auto_now_add=True)
	image = models.ImageField("Имаге", blank=True)
	likes = models.ManyToManyField(Profile, verbose_name="Классы", blank=True, related_name='profile_liked')

	def get_likes(self):
		return self.likes.all()
	@property
	def likes_count(self):
		return self.likes.all().count()
	def __str__(self) -> str:
		return str(self.author)
	class Meta():
		ordering = ["-created_at"]

class Tag(models.Model):

	name = models.CharField("Тег", unique=True, default=None, max_length=50)
	posts = models.ManyToManyField(Post, blank=True)