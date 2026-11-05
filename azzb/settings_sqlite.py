"""Только для переезда прода с SQLite на PostgreSQL (docs/deploy/postgres.md).

Читает старую базу azzb/db.sqlite3, чтобы выгрузить из неё данные:
    python manage.py dumpdata ... --settings=azzb.settings_sqlite
Им же можно временно запустить сайт на старой базе, если переезд пришлось откатить.
После переезда файл можно удалить.
"""
import os

# Основные настройки требуют POSTGRES_DB; здесь база всё равно подменяется ниже.
os.environ.setdefault('POSTGRES_DB', 'unused-sqlite-dump')

from .settings import *  # noqa: E402,F401,F403

DATABASES = {
	'default': {
		'ENGINE': 'django.db.backends.sqlite3',
		'NAME': BASE_DIR / 'db.sqlite3',  # noqa: F405
	}
}
