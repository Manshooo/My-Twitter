# Generated by Django 4.2 on 2023-08-25 12:01

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Twitter', '0002_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='post',
            name='post_date',
            field=models.DateTimeField(blank=True, verbose_name='Дата публикации'),
        ),
        migrations.AlterField(
            model_name='post',
            name='post_text',
            field=models.TextField(blank=True, default='', verbose_name='Текст поста'),
        ),
    ]