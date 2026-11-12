# Переход на Docker, картинки в S3, копии в S3 (A10)

Было: nginx → uWSGI (сервис `azzb`, код и `venv` в `/var/www/azzb`) → PostgreSQL; картинки
на диске, дамп базы раз в сутки на тот же диск.

Стало:

```
push в main → тесты → образ ghcr.io/manshooo/my-twitter → раннер на сервере → /srv/azzb/deploy.sh
nginx (хост) ─┬─ /        → gunicorn в контейнере, 127.0.0.1:8001 → PostgreSQL и Postfix хоста
              ├─ /ws/     → uvicorn в контейнере, 127.0.0.1:8002 (после 2 ГБ памяти, realtime.md)
              └─ /media/  → бакет Selectel azzb-media (с кэшем на диске)
cron 03:30 → /srv/azzb/backup.sh → бакет azzb-backups: дамп базы (зашифрован), копия картинок; 30 дней
```

- **PostgreSQL, Postfix, nginx и certbot остаются на хосте.** Контейнер работает в сети хоста
  (`network_mode: host`), поэтому база и почта доступны ему как раньше, по `localhost`.
- **Статика** лежит в образе и отдаётся приложением (whitenoise) с хешем в имени, поэтому nginx
  её больше не раздаёт. `azzb.css` и `azzb.js` собирает esbuild из `frontend/` на первой стадии
  образа (Node есть только там) — см. `docs/frontend.md`.
- **Ошибки 500** приходят письмом на адреса из `ADMINS`. О том, что сайт лёг совсем, сообщает
  uptime-чекер manshoo.ru: он уже следит за `https://azzb.ru`.

Порядок ниже рассчитан на переезд без простоя: новый контейнер поднимается рядом с uWSGI, nginx
переключается одной командой, и до шага 8 можно вернуться назад (раздел 10).

## 1. GitHub

1. **Чужие PR не должны запускаться на сервере.** Settings → Actions → General → «Fork pull request
   workflows from outside collaborators» → **Require approval for all external contributors**.
   По умолчанию одобрение нужно только тем, кто пишет впервые, а PR из форка может принести
   свой workflow с `runs-on: self-hosted`. То же стоит включить в репозитории manshoo.ru.
2. **Образ.** После слияния этого PR CI соберёт и опубликует `ghcr.io/manshooo/my-twitter`.
   Сделайте пакет публичным (профиль → Packages → my-twitter → Package settings → Change
   visibility → Public). Секретов в образе нет, а сервер сможет скачивать его без входа.
3. **Автовыкладка** включается переменной: Settings → Secrets and variables → Actions → Variables →
   `AZZB_DEPLOY` = `on`. Включайте после шага 7: без неё джоба выкладки просто пропускается.

## 2. Раннер на сервере

Раннер привязан к репозиторию, поэтому для My-Twitter нужен свой, отдельный от раннера manshoo.ru.
Он работает под `azzb_user`, а `azzb_user` нужен доступ к Docker:

```bash
sudo usermod -aG docker azzb_user
```

Доступ к Docker равен правам root на сервере. Именно поэтому важна настройка из шага 1.1.

GitHub → Settings → Actions → Runners → New self-hosted runner → Linux x64. Команды скачивания
оттуда выполните под `azzb_user` в `~/actions-runner`, а настройку — с меткой `azzb`:

```bash
./config.sh --url https://github.com/Manshooo/My-Twitter --token ТОКЕН_СО_СТРАНИЦЫ --name azzb-vps --labels azzb --unattended
sudo ./svc.sh install azzb_user && sudo ./svc.sh start
```

## 3. Каталог /srv/azzb

```bash
sudo install -d -o azzb_user -g azzb_user -m 750 /srv/azzb
sudo -u azzb_user cp /var/www/azzb/.env /srv/azzb/.env
sudo chmod 600 /srv/azzb/.env
id azzb_user
```

Допишите в `/srv/azzb/.env` (значения S3 — после раздела 4):

```ini
# uid и gid из `id azzb_user`: контейнер работает от этого пользователя и читает .env.
AZZB_UID=
AZZB_GID=
# Кому письмо об ошибке 500. Кавычки — вокруг всего значения: его читают и Docker Compose, и Django.
ADMINS='Ваше имя <ваш@адрес>'
S3_MEDIA_BUCKET=azzb-media
S3_ENDPOINT=https://s3.ru-6.storage.selcloud.ru
S3_REGION=ru-6
S3_ADDRESSING_STYLE=virtual
S3_ACCESS_KEY=
S3_SECRET_KEY=
```

**Знак `$` в значениях.** Docker Compose читает этот же `.env` и подставляет в нём `$ИМЯ`. Проверьте:

```bash
grep -n '\$' /srv/azzb/.env
```

Если что-то нашлось, например в `DJANGO_SECRET_KEY`, заключите значение в одинарные кавычки:
`DJANGO_SECRET_KEY='…'`. Так значение не меняется ни для Compose, ни для Django.

**Пароль базы для копий.** `deploy.sh` и `backup.sh` вызывают `pg_dump` на хосте. Под `azzb_user`:

```bash
echo "localhost:5432:azzb:azzb:ПАРОЛЬ_ИЗ_POSTGRES_PASSWORD" > ~/.pgpass && chmod 600 ~/.pgpass
```

Если база или пользователь называются не `azzb`, укажите свои в `~/.pgpass`. Затем добавьте
`PGUSER=…` и `PGDATABASE=…` в `~/actions-runner/.env` и в начало crontab (раздел 8).

**Размер журнала.** Он уже занимал 1,2 ГБ, а теперь туда пишет и контейнер:

```bash
sudo mkdir -p /etc/systemd/journald.conf.d
sudo curl -fsSLo /etc/systemd/journald.conf.d/size.conf https://raw.githubusercontent.com/Manshooo/My-Twitter/main/deploy/journald.conf
sudo systemctl restart systemd-journald
```

## 4. Selectel: бакеты, ключ, шифрование копий

**Бакеты** (адресация vHosted; пулы могут быть разными — у каждого свой адрес S3 API, его
показывает вкладка «Подключение»). Имена бакетов глобальные: если ваши отличаются (например,
`azzb-media-1`), подставляйте их везде ниже вместо `azzb-media` и `azzb-backups`:

| Бакет | Класс | Доступ |
|---|---|---|
| `azzb-media` | стандартный | публичный: картинки и сейчас открыты по ссылке |
| `azzb-backups` | холодный, если пул его предлагает, иначе стандартный | **приватный** |

**Без версионирования и Object Lock** — в обоих бакетах. С версионированием удаление файла только
прячет его, а старая версия остаётся навсегда: картинки стёртых постов и аккаунтов не стирались бы
на самом деле (это противоречит политике конфиденциальности), а место росло бы. Object Lock
отключить нельзя, и версионирование при нём не выключается — такой бакет только пересоздавать.
От ошибок и поломок защищают ночные копии.

Удалять старые копии будет `backup.sh`, правила жизненного цикла в бакете не нужны. Политику
доступа, Cache-Control, CORS и «Веб-сайт» не настраивайте: заголовок кэша сайт пишет в каждый файл
сам, а с политикой Selectel запрещает всё, что в ней явно не разрешено, — легко отрезать доступ
самому сайту.

**Публичный домен.** Без ключа Selectel отдаёт файлы только через публичный домен бакета вида
`<uuid>.selstorage.ru` (вкладка «Домены»), а не через `azzb-media.s3.ru-6.storage.selcloud.ru` —
тот только для запросов с ключом. Этот домен понадобится nginx (шаг 7). Проверьте, что список
файлов по нему не отдаётся:

```bash
curl -s https://ВАШ-UUID.selstorage.ru/ | head -c 300
```

Если в ответе `ListBucketResult` с именами файлов — список открыт любому, кто узнает домен (на
страницах сайта его нет: картинки идут через azzb.ru). Тогда напишите — подберём другую схему.

**Ключ.** В панели Selectel создайте сервисного пользователя с доступом к объектному хранилищу
проекта и выпустите ему S3-ключ. Пара Access key и Secret key пойдёт в `.env`
(`S3_ACCESS_KEY`, `S3_SECRET_KEY`) и в настройку rclone ниже.

Один ключ на оба бакета — компромисс: при взломе сервера им можно удалить и картинки, и копии.
Поэтому раз в месяц скачивайте свежий дамп к себе (раздел 9).

**rclone и age** на сервере. rclone нужен не старше 1.69 (так советует Selectel), а в Debian 12
из apt ставится 1.60, поэтому — пакет с сайта rclone:

```bash
sudo apt install age
curl -fsSLO https://downloads.rclone.org/rclone-current-linux-amd64.deb
sudo apt install ./rclone-current-linux-amd64.deb && rm rclone-current-linux-amd64.deb
rclone version | head -1
```

Сам он не обновляется: раз в несколько месяцев — `sudo rclone selfupdate`.

От `azzb_user` создайте `~/.config/rclone/rclone.conf` с правами `chmod 600`. По разделу на пул:
`endpoint` и `region` — с вкладки «Подключение» каждого бакета (ниже — медиа в ru-6, копии в ru-7):

```ini
[media]
type = s3
provider = Other
access_key_id = ВАШ_ACCESS_KEY
secret_access_key = ВАШ_SECRET_KEY
endpoint = https://s3.ru-6.storage.selcloud.ru
region = ru-6
force_path_style = false

[backups]
type = s3
provider = Other
access_key_id = ВАШ_ACCESS_KEY
secret_access_key = ВАШ_SECRET_KEY
endpoint = https://s3.ru-7.storage.selcloud.ru
region = ru-7
force_path_style = false
```

Проверка: `rclone lsd media:` и `rclone lsd backups:` — в каждом виден свой бакет.

Копии в другом пуле надёжнее (другая площадка), но картинки тогда копируются через сервер:
исходящий трафик Selectel платный, а ночью копируются только новые файлы — копейки.

**Ключ шифрования копий** создаётся **на вашем компьютере**: на Windows `winget install FiloSottile.age`,
затем

```bash
age-keygen -o azzb-backup.key
```

Команда печатает открытый ключ `age1…`. Его положите на сервер:

```bash
echo "age1…" > /srv/azzb/backup-key.pub
```

Файл `azzb-backup.key` — единственный способ прочитать копии. На сервер его не кладите, а
храните в менеджере паролей и ещё в одном месте. Потеряете ключ — копии превратятся в мусор.

## 5. Картинки в бакет

Имя бакета — ваше, как в панели (если пришлось взять `azzb-media-1`, то оно). rclone сам создаёт
бакет, которого нет, поэтому опечатка в имени не даёт ошибки, а молча заводит новый бакет.

```bash
rclone copy /var/www/azzb/media media:azzb-media --progress \
    --header-upload "Cache-Control: public, max-age=31536000, immutable"
rclone ls media:azzb-media | head -3
```

Число объектов в панели у бакета должно совпасть с числом скопированных файлов. Затем откройте один из
файлов по публичному домену (путь — из вывода `rclone ls`):

```bash
curl -sI https://ВАШ-UUID.selstorage.ru/ПУТЬ/К/ФАЙЛУ.webp | head -1
```

Ответ — `200`. Если `403`, бакет не публичный (тип бакета в панели). Файла
`default/default_user_avatar.jpg` может и не быть: сайт его не показывает, вместо аватара по умолчанию — буква.

## 6. Первый запуск контейнера (рядом с uWSGI)

Пока раннер не выкладывает сам, файлы берутся из репозитория:

```bash
cd /srv/azzb
for f in docker-compose.prod.yml deploy/deploy.sh deploy/backup.sh deploy/manage.sh; do
  curl -fsSLO https://raw.githubusercontent.com/Manshooo/My-Twitter/main/$f
done
chmod +x deploy.sh backup.sh manage.sh
./deploy.sh latest
```

`deploy.sh` делает копию базы, скачивает образ, применяет миграции, запускает контейнер и
проверяет `/healthz`. Сайт в это время работает на uWSGI, а контейнер слушает только `127.0.0.1:8001`.

```bash
docker compose -f docker-compose.prod.yml ps        # web — healthy
journalctl -t azzb-web -n 20 --no-pager
./manage.sh sendtestemail ваш@адрес                 # почта из контейнера
```

## 7. Переключение nginx

```bash
sudo cp /etc/nginx/sites-available/azzb ~/azzb.nginx.uwsgi
```

Возьмите [deploy/nginx/azzb.conf](../../deploy/nginx/azzb.conf) и подставьте два значения:
- `Strict-Transport-Security` в трёх строках — итоговый, с `includeSubDomains` и `preload`
  (security.md, раздел 5); если HSTS ещё на начальных шагах — свой `max-age` без этих двух слов;
- публичный домен бакета (`<uuid>.selstorage.ru`) в двух строках `/media/`.

Блок `default_server`, если он у вас в этом файле, оставьте. Затем — папка для кэша картинок
(пакет nginx в Debian её не создаёт, а nginx создаёт только последний уровень пути) и проверка:

```bash
sudo mkdir -p /var/cache/nginx
sudo nginx -t && sudo systemctl reload nginx
```

С этого момента сайт обслуживает контейнер. Проверьте:

1. `curl -sI https://azzb.ru | head -1` — `HTTP/2 200`.
2. `curl -sI https://azzb.ru/media/ПУТЬ/К/ФАЙЛУ.webp | grep -i x-cache` (файл из шага 5) — `MISS`, при
   повторе `HIT`.
3. Вход, пост с картинкой (картинка появилась в бакете: `rclone ls media:azzb-media/posts | tail -1`),
   смена аватара, удаление поста.
4. В админке, в «Журнале действий», у вашего входа стоит ваш настоящий IP.

Если что-то не так, верните прежний конфиг (раздел 10) и пришлите `journalctl -t azzb-web -n 100`.

Картинки, которые загрузили через uWSGI между шагами 5 и 7, догрузите повторно (rclone
копирует только новые):

```bash
rclone copy /var/www/azzb/media media:azzb-media --header-upload "Cache-Control: public, max-age=31536000, immutable"
```

Включите автовыкладку (шаг 1.3).

## 8. uWSGI — выключить, cron — заменить

```bash
sudo systemctl disable --now azzb
```

Старые задания удалите: дамп в crontab пользователя `postgres` (`sudo crontab -u postgres -e`)
и `purge_expired` в crontab `azzb_user`. Новые — в `crontab -e` под `azzb_user`:

```cron
AZZB_MEDIA=media:azzb-media
AZZB_BACKUP=backups:azzb-backups
30 3 * * * /srv/azzb/backup.sh >> /srv/azzb/backups/backup.log 2>&1
15 4 * * * /srv/azzb/manage.sh purge_expired >> /srv/azzb/backups/purge.log 2>&1
```

Запустите копию сразу, не дожидаясь ночи, и проверьте, что она дошла:

```bash
AZZB_MEDIA=media:azzb-media AZZB_BACKUP=backups:azzb-backups /srv/azzb/backup.sh && rclone ls backups:azzb-backups/db
```

**Через неделю**, если всё работает, удалите старое:

```bash
sudo rm -rf /var/www/azzb /var/backups/azzb
sudo apt purge uwsgi uwsgi-plugin-python3
sudo rm /etc/systemd/system/azzb.service
sudo systemctl daemon-reload
```

`/etc/uwsgi/` после `purge` удалите, если там остался конфиг сайта.

## 9. Восстановление из копии

Проверяйте копию один раз сразу после настройки, потом раз в несколько месяцев — **на своём
компьютере**: копия, из которой ни разу не восстанавливали, — не копия. Полная проверка —
восстановить дамп в пустую базу локального PostgreSQL (в pgAdmin: новая база → Restore, формат
Custom, «Do not save: Owner»), посмотреть таблицы и удалить базу.

На своём компьютере. Свежий дамп проще всего скачать из панели Selectel: бакет копий → «Объекты» →
`db/` → файл → «Скачать». Или rclone (на Windows — `winget install Rclone.Rclone`, затем раздел
`[backups]` из `rclone.conf` сервера в файл, который покажет `rclone config file`):

```bash
rclone copy backups:azzb-backups/db/azzb-ГГГГ-ММ-ДД.dump.age .
age --decrypt -i azzb-backup.key -o azzb.dump azzb-ГГГГ-ММ-ДД.dump.age
pg_restore --list azzb.dump | head
```

`-o` вместо `> azzb.dump`: в PowerShell перенаправление может испортить двоичный файл. Расшифровался —
значит, ключ подходит. Без PostgreSQL на компьютере (`pg_restore`) достаточно увидеть начало файла:
в PowerShell `Format-Hex azzb.dump -Count 16` — первые буквы `PGDMP`.

Проверка на этом заканчивается. Дальше — **только при аварии**, когда база или картинки потеряны:
восстановление заменяет всё текущее содержимым копии, и сделанное пользователями после неё пропадёт.

**База** на сервере. Расшифрованный `azzb.dump` сначала скопируйте с компьютера в `/srv/azzb`
(`scp azzb.dump azzb_user@azzb.ru:/srv/azzb/`): ключа для расшифровки на сервере нет. Сайт на это время остановлен:

```bash
cd /srv/azzb && docker compose -f docker-compose.prod.yml stop web
pg_restore --clean --if-exists -h localhost -U azzb -d azzb azzb.dump
docker compose -f docker-compose.prod.yml start web
```

**Картинки:**

```bash
rclone copy backups:azzb-backups/media media:azzb-media
```

Файлы, стёртые сайтом за последние 30 дней, лежат в `azzb-backups/media-deleted/<дата>/`.

## 10. Откат на uWSGI (до удаления старого на шаге 8)

```bash
sudo cp ~/azzb.nginx.uwsgi /etc/nginx/sites-available/azzb
sudo systemctl enable --now azzb
sudo nginx -t && sudo systemctl reload nginx
rclone copy media:azzb-media /var/www/azzb/media
```

Последняя команда забирает картинки, загруженные уже в бакет. Старый код читает их с диска.

Откатить только версию сайта, оставаясь на Docker: `/srv/azzb/deploy.sh <SHA прошлого коммита>`.
Прошлая версия записана в `/srv/azzb/.deployed-tag` до выкладки; при ошибке `deploy.sh` сам печатает
команду отката.

## Память

На сервере 1 ГБ. На нём manshoo.ru (четыре контейнера), PostgreSQL, Postfix, два раннера и
gunicorn AzzB: 2 процесса по 4 потока, около 150–200 МБ. После выключения uWSGI его память
освобождается, так что сейчас должно хватить. Redis и процесс для WebSocket (этап 4) по умолчанию
выключены: включайте их по [realtime.md](realtime.md) после перехода на тариф с 2 ГБ. Следить: `free -h`, `docker stats --no-stream`.
