# Переезд прода с SQLite на PostgreSQL

Сайт работает **только на PostgreSQL**: без переменной `POSTGRES_DB` он не запустится. Поэтому выкладка новой версии и переезд базы — одна операция. Пока она не сделана, на сервере остаётся старый код.

Старая база `azzb/db.sqlite3` после этого доступна только через отдельные настройки `azzb.settings_sqlite`: ими делается дамп, и ими же можно временно запустить сайт, если переезд придётся откатить.

Команды рассчитаны на Debian 12 и запуск из каталога `azzb/` (где лежит `manage.py`) в виртуальном окружении проекта. Пути и имя сервиса (`azzb`) замените на свои.

## 0. Заранее: установить PostgreSQL и создать базу

Сайт в это время работает как обычно.

```bash
sudo apt install postgresql
sudo -u postgres createuser --pwprompt azzb
sudo -u postgres createdb --owner azzb --encoding UTF8 --template template0 azzb
```

В Debian 12 это PostgreSQL 15 — на нём же гоняются тесты в CI.

## 1. Остановить сайт и сделать резервную копию

```bash
sudo systemctl stop azzb
cp db.sqlite3 ~/db.sqlite3.before-postgres
```

## 2. Выложить новый код

```bash
git pull
pip install -r ../requirements.txt
```

## 3. Довести старую базу до текущей схемы и выгрузить данные

Дамп и новая база должны быть на одной версии схемы, поэтому сначала миграции на SQLite:

```bash
python manage.py migrate --settings=azzb.settings_sqlite
python manage.py dumpdata --settings=azzb.settings_sqlite --natural-foreign \
  --exclude contenttypes --exclude auth.permission \
  --exclude admin.logentry --exclude sessions \
  --indent 2 --output ~/azzb-data.json
```

- `--natural-foreign` ссылается на права и типы контента по именам, а не по id: в новой базе их id будут другими.
- **Не добавляйте `--natural-primary`**: посты ссылаются на профиль по id пользователя, и id должны остаться прежними.
- Сессии не переносим: все пользователи один раз перезайдут.

## 4. Создать схему в PostgreSQL и загрузить данные

Пропишите в `azzb/.env` переменные из `.env.example`: `POSTGRES_DB=azzb`, `POSTGRES_USER=azzb`, `POSTGRES_PASSWORD=…`, `POSTGRES_HOST=localhost`. Затем:

```bash
python manage.py migrate
python manage.py loaddata ~/azzb-data.json
```

`loaddata` записывает строки с исходными id, а счётчики автоинкремента в PostgreSQL при этом не двигаются. Без следующей команды первая же регистрация упадёт с ошибкой «duplicate key»:

```bash
python manage.py sqlsequencereset customUser auth post | python manage.py dbshell
```

## 5. Проверить

Сравните количество записей в новой и старой базе:

```bash
python manage.py shell -c "from customUser.models import CustomUser; from post.models import Post, Like; print(CustomUser.objects.count(), Post.objects.count(), Like.objects.count())"
python manage.py shell --settings=azzb.settings_sqlite -c "from customUser.models import CustomUser; from post.models import Post, Like; print(CustomUser.objects.count(), Post.objects.count(), Like.objects.count())"
```

Числа должны совпасть. Затем запустите сайт (`sudo systemctl start azzb`), войдите, опубликуйте и удалите пост, поставьте лайк.

## 6. Если что-то пошло не так

Запустите сайт на старой базе: добавьте в unit-файл сервиса `Environment=DJANGO_SETTINGS_MODULE=azzb.settings_sqlite`, затем `sudo systemctl daemon-reload && sudo systemctl start azzb`. `db.sqlite3` после шага 3 содержит все данные; исходная копия лежит в `~/db.sqlite3.before-postgres`.

## После переезда

- Удалите `azzb/azzb/settings_sqlite.py` и `db.sqlite3`, когда убедитесь, что всё работает (копию лучше сохранить где-нибудь ещё).
- Ежедневный дамп с хранением 14 дней. Добавьте в `crontab -e` пользователя `postgres`:

```cron
30 3 * * * pg_dump --format=custom azzb > /var/backups/azzb/azzb-$(date +\%F).dump && find /var/backups/azzb -name '*.dump' -mtime +14 -delete
```

Каталог `/var/backups/azzb` нужно создать заранее и отдать пользователю `postgres`. Восстановление: `pg_restore --clean --dbname azzb azzb-ГГГГ-ММ-ДД.dump`. Резервные копии на том же диске не спасут от поломки сервера, поэтому периодически копируйте их на другую машину. Полностью это закрывает пункт A10.
