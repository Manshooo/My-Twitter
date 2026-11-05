# Переезд прода с SQLite на PostgreSQL

Сайт выбирает базу по переменной `POSTGRES_DB`: если она задана, используется PostgreSQL, если пустая — SQLite (`azzb/db.sqlite3`). Поэтому откат — это просто убрать `POSTGRES_*` из `.env` и перезапустить сайт.

Команды ниже рассчитаны на Debian 12 и запуск из каталога `azzb/` (где лежит `manage.py`) в виртуальном окружении проекта. Пути и имя сервиса (`azzb`) замените на свои.

## 0. Подготовка

1. Выкатите текущий `main` и обновите зависимости: `pip install -r ../requirements.txt` (нужен драйвер `psycopg`).
2. Примените миграции **на старой SQLite**: `python manage.py migrate`. Дамп и новая база должны быть на одной версии схемы.

## 1. Установить PostgreSQL и создать базу

```bash
sudo apt install postgresql
sudo -u postgres createuser --pwprompt azzb
sudo -u postgres createdb --owner azzb --encoding UTF8 --template template0 azzb
```

## 2. Остановить запись и сделать резервные копии

Остановите сайт, чтобы за время переезда никто ничего не написал:

```bash
sudo systemctl stop azzb
cp db.sqlite3 ~/db.sqlite3.before-postgres
```

## 3. Выгрузить данные из SQLite

Переменные `POSTGRES_*` пока **не** задаём — команда работает со старой базой.

```bash
python manage.py dumpdata --natural-foreign \
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

```bash
python manage.py shell -c "from customUser.models import CustomUser, Profile; from post.models import Post; print(CustomUser.objects.count(), Profile.objects.count(), Post.objects.count())"
```

Сравните числа с теми же командами на SQLite (без `POSTGRES_*`). Затем запустите сайт (`sudo systemctl start azzb`), войдите, опубликуйте и удалите пост, поставьте лайк.

## 6. Если что-то пошло не так

Уберите `POSTGRES_*` из `.env` и перезапустите сайт: он снова работает на `db.sqlite3`, который не менялся. Копия лежит в `~/db.sqlite3.before-postgres`.

## После переезда: резервные копии

Ежедневный дамп с хранением 14 дней. Добавьте в `crontab -e` пользователя `postgres`:

```cron
30 3 * * * pg_dump --format=custom azzb > /var/backups/azzb/azzb-$(date +\%F).dump && find /var/backups/azzb -name '*.dump' -mtime +14 -delete
```

Каталог `/var/backups/azzb` нужно создать заранее и отдать пользователю `postgres`. Восстановление: `pg_restore --clean --dbname azzb azzb-ГГГГ-ММ-ДД.dump`. Резервные копии на том же диске не спасут от поломки сервера, поэтому периодически копируйте их на другую машину. Полностью это закрывает пункт A10.
