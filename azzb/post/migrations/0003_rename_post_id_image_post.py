# Generated by Django 5.0.1 on 2024-01-26 17:56

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('post', '0002_remove_post_unique_image_remove_image_image_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='image',
            old_name='post_id',
            new_name='post',
        ),
    ]
