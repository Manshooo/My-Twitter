"""Теги и упоминания для постов, опубликованных до D2. Уведомления о старых упоминаниях не шлём."""
import re

from django.db import migrations

# Копия разбора из post/text.py на момент миграции: код приложения со временем меняется, миграция — нет.
HASHTAG_RE = re.compile(r'(?<![\w#])#(\w{1,64})')
MENTION_RE = re.compile(r'(?<![\w@])@([a-zA-Z0-9_.-]{1,30})')


def backfill(apps, schema_editor):
	Post = apps.get_model('post', 'Post')
	Hashtag = apps.get_model('post', 'Hashtag')
	PostHashtag = apps.get_model('post', 'PostHashtag')
	Mention = apps.get_model('post', 'Mention')
	Profile = apps.get_model('customUser', 'Profile')
	posts = Post.objects.filter(deleted_at__isnull=True).exclude(text='').filter(text__regex=r'[#@]')
	for post in posts.iterator():
		names = {name.lower() for name in HASHTAG_RE.findall(post.text) if not name.replace('_', '').isdigit()}
		for name in names:
			tag, _ = Hashtag.objects.get_or_create(name=name)
			PostHashtag.objects.get_or_create(post=post, hashtag=tag)
		logins = {login.rstrip('.-') for login in MENTION_RE.findall(post.text)}
		for profile in Profile.objects.filter(user__username__in=logins).exclude(user_id=post.author_id):
			Mention.objects.get_or_create(post=post, profile=profile)


class Migration(migrations.Migration):
	dependencies = [('post', '0015_hashtags_mentions'), ('customUser', '0011_customuser_deleted_at_customuser_erased_at')]
	operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
