"""Таблица кэша azzb_cache (CACHES в settings.py): на ней держатся лимиты частоты (E2).

createcachetable — отдельная команда, её легко забыть при выкладке; в миграции таблица
появится сама при `manage.py migrate`. Команда ничего не делает, если таблица уже есть.
"""
from django.core.management import call_command
from django.db import migrations


def create_cache_table(apps, schema_editor):
	call_command('createcachetable', database=schema_editor.connection.alias, verbosity=0)


class Migration(migrations.Migration):

	dependencies = []

	operations = [
		migrations.RunPython(create_cache_table, migrations.RunPython.noop),
	]
