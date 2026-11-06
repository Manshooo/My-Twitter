"""Группа «Модераторы» с правом moderation.moderate (E4).

Модератора назначают в админке: Пользователи → Группы → Модераторы. Права staff для этого
не нужны — очередь жалоб живёт на сайте (/moderation/), а не в админке.
"""
from django.contrib.auth.management import create_permissions
from django.db import migrations

GROUP = 'Модераторы'


def forwards(apps, schema_editor):
	# Права создаются сигналом после всех миграций — здесь их ещё может не быть.
	config = apps.get_app_config('moderation')
	config.models_module = True
	create_permissions(config, apps=apps, verbosity=0)
	config.models_module = None

	Group = apps.get_model('auth', 'Group')
	Permission = apps.get_model('auth', 'Permission')
	group, _ = Group.objects.get_or_create(name=GROUP)
	group.permissions.add(Permission.objects.get(content_type__app_label='moderation', codename='moderate'))


def backwards(apps, schema_editor):
	apps.get_model('auth', 'Group').objects.filter(name=GROUP).delete()


class Migration(migrations.Migration):

	dependencies = [
		('moderation', '0001_initial'),
		('auth', '0012_alter_user_first_name_max_length'),
		('contenttypes', '0002_remove_content_type_name'),
	]

	operations = [
		migrations.RunPython(forwards, backwards),
	]
