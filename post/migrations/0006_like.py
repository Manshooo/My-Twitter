# Лайки: автоматическая связь Post.likes → явная модель Like с created_at.
#
# 1) SeparateDatabaseAndState: модель Like садится на уже существующую таблицу
#    post_post_likes (те же колонки и уникальный индекс), в базе ничего не меняется.
# 2) Добавляем колонку created_at.
# 3) Настоящее время старых лайков неизвестно — ставим им время публикации поста:
#    это нижняя граница, и старые лайки не выглядят «свежими» для «Горячего».

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models
from django.db.models import OuterRef, Subquery


def backfill_like_dates(apps, schema_editor):
	Like = apps.get_model('post', 'Like')
	Post = apps.get_model('post', 'Post')
	post_created = Post.objects.filter(pk=OuterRef('post_id')).values('created_at')[:1]
	Like.objects.update(created_at=Subquery(post_created))


class Migration(migrations.Migration):

	dependencies = [
		('customUser', '0003_follows_through_fields'),
		('post', '0005_alter_image_post'),
	]

	operations = [
		migrations.SeparateDatabaseAndState(
			database_operations=[],
			state_operations=[
				migrations.CreateModel(
					name='Like',
					fields=[
						('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
						('post', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='post.post')),
						('profile', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='customUser.profile')),
					],
					options={
						'verbose_name': 'Лайк',
						'verbose_name_plural': 'Лайки',
						'db_table': 'post_post_likes',
						'unique_together': {('post', 'profile')},
					},
				),
				migrations.AlterField(
					model_name='post',
					name='likes',
					field=models.ManyToManyField(blank=True, related_name='profile_liked', through='post.Like', to='customUser.profile', verbose_name='Классы'),
				),
			],
		),
		migrations.AddField(
			model_name='like',
			name='created_at',
			field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now, verbose_name='Когда поставлен'),
			preserve_default=False,
		),
		migrations.RunPython(backfill_like_dates, migrations.RunPython.noop),
	]
