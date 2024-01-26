# Generated by Django 5.0.1 on 2024-01-26 17:20

import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('customUser', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Post',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('text', models.TextField(blank=True, default='', verbose_name='Текст поста')),
                ('updated', models.DateTimeField(auto_now=True, verbose_name='Дата обновления')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Дата публикации')),
                ('image', models.ImageField(blank=True, null=True, upload_to='images', verbose_name='Имагес')),
                ('author', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='posts', to='customUser.profile', to_field='user')),
                ('likes', models.ManyToManyField(blank=True, related_name='profile_liked', to='customUser.profile', verbose_name='Классы')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='Image',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('image', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='images', to='post.post', to_field='image')),
            ],
        ),
        migrations.AddConstraint(
            model_name='post',
            constraint=models.UniqueConstraint(fields=('image',), name='unique_image'),
        ),
    ]
