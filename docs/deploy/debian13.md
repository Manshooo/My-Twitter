# Переход с Debian 12 на Debian 13 (trixie)

Сервер: Debian 12, nginx 1.22, uWSGI 2.0.21 из пакетов Debian, PostgreSQL 15, Python 3.11,
1 ГБ памяти, 15 ГБ диска. Debian 13 приносит nginx 1.26, PostgreSQL 17 и Python 3.13: сайт
на них проверен (CI гоняет тесты на 3.13), но базу и виртуальное окружение придётся перенести.

**Снимка VPS нет**, поэтому откатить обновление нельзя — только поставить систему заново и
восстановить всё из копий. Поэтому шаг 2 (копии на свой компьютер) обязателен, а не на всякий случай.

**Если сайт уже переехал в Docker** ([docker.md](docker.md)): шаг 6 не нужен — Python сайта
живёт в образе и от системного не зависит; после перезагрузки контейнер поднимется сам. Docker из
репозитория Docker тоже переключите на trixie на шаге 4 (`/etc/apt/sources.list.d/docker.list`).

Займёт 1–2 часа, сайт недоступен примерно полчаса. Делайте, когда есть время разобраться,
если что-то пойдёт не так.

## 0. Сначала, отдельно и заранее: обновить Debian 12 до конца

На сервере установлено новое ядро (`6.1.0-54`), а работает старое (`6.1.0-48`): исправления
безопасности ядра не действуют до перезагрузки. И 6 пакетов ждут обновления. Это стоит сделать
сейчас, независимо от перехода на Debian 13.

Проверить, что всё нужное само запустится после перезагрузки (везде должно быть `enabled`):

```bash
systemctl is-enabled nginx postgresql azzb postfix opendkim
```

Обновить и перезагрузить:

```bash
sudo apt update && sudo apt full-upgrade
sudo reboot
```

После перезагрузки — `uname -r` (должно быть `6.1.0-54-amd64`), `systemctl --failed` (пусто),
сайт открывается, письма уходят (`python manage.py sendtestemail ваш@адрес`). Старое ядро:

```bash
sudo apt autoremove
```

## 1. Место на диске

Свободно 3,1 ГБ из 15. Обновлению нужно 2–3 ГБ под пакеты и место под копию базы при переносе
PostgreSQL. Сначала посмотрите, что занимает место:

```bash
sudo du -xh / --max-depth=2 2>/dev/null | sort -h | tail -20
sudo -u postgres psql -tAc "SELECT pg_size_pretty(pg_database_size('azzb'));"
journalctl --disk-usage
```

Что обычно можно освободить:

```bash
sudo apt clean                          # кэш скачанных пакетов
sudo journalctl --vacuum-size=200M      # старые системные журналы
ls -lh /var/backups/azzb/               # ежедневные дампы базы: хранятся 14 дней
rm -rf /var/www/azzb/venv.old           # если пересоздавали окружение (security.md, раздел 6)
```

Цель — **не меньше 5 ГБ свободно** плюс размер базы.

## 2. Копии на свой компьютер

На сервере, от `root` (`sudo -i`). Архив собирается в домашней папке `azzb_user`, чтобы его
можно было скачать под этим пользователем:

```bash
mkdir -p /home/azzb_user/azzb-backup && cd /home/azzb_user/azzb-backup
sudo -u postgres pg_dumpall --globals-only > pg-globals.sql     # роли и пароли PostgreSQL
sudo -u postgres pg_dump --format=custom azzb > azzb.dump
tar czf media.tgz -C /var/www/azzb media
tar czf etc.tgz /etc/nginx /etc/uwsgi /etc/systemd/system /etc/postfix /etc/opendkim* \
    /etc/letsencrypt /etc/apt /etc/cron.d /etc/unattended-upgrades 2>/dev/null
cp /var/www/azzb/.env env.txt
crontab -l -u postgres > crontab-postgres.txt 2>/dev/null
crontab -l -u azzb_user > crontab-azzb_user.txt 2>/dev/null
dpkg --get-selections > packages.txt
cd /home/azzb_user && tar cf azzb-backup.tar azzb-backup && rm -rf azzb-backup
chown azzb_user: azzb-backup.tar && chmod 600 azzb-backup.tar && ls -lh azzb-backup.tar
```

В `etc.tgz` — ключ DKIM (`/etc/opendkim*`) и сертификаты: без ключа DKIM после переустановки
придётся заново публиковать DNS-запись и ждать, пока она разойдётся. В `env.txt` — пароли.
Храните архив так же бережно, как пароль от сервера.

Скачать к себе (на своём компьютере):

```bash
scp azzb_user@azzb.ru:azzb-backup.tar .
```

Проверьте, что архив открывается: `tar tf azzb-backup.tar | head`. Если на компьютере есть
PostgreSQL — что дамп читается: `pg_restore --list azzb.dump | head`. Когда архив у вас,
удалите его с сервера (`rm /home/azzb_user/azzb-backup.tar`): он занимает место, нужное обновлению.

## 3. Подготовка

Сторонние источники пакетов — каждый нужно будет переключить на trixie или отключить:

```bash
grep -rh "^deb\|^URIs\|^Suites" /etc/apt/sources.list /etc/apt/sources.list.d/
```

Обновление идёт через SSH: если связь оборвётся посреди установки пакетов, система может
остаться полуобновлённой. Запускайте всё внутри `screen` (после обрыва — `screen -r`), а в
панели FirstVDS заранее найдите консоль VNC: через неё можно попасть на сервер, если SSH не поднимется.

```bash
sudo apt install screen
screen -S upgrade
```

## 4. Обновление

```bash
sudo systemctl stop azzb
sudo sed -i 's/bookworm/trixie/g' /etc/apt/sources.list /etc/apt/sources.list.d/*.list /etc/apt/sources.list.d/*.sources 2>/dev/null
grep -rh "bookworm\|trixie" /etc/apt/sources.list /etc/apt/sources.list.d/   # везде trixie
sudo apt update
sudo apt upgrade --without-new-pkgs
sudo apt full-upgrade
```

Вопросы при установке:

- **«Изменённый файл настроек… установить версию сопровождающего?»** — для nginx, Postfix,
  OpenDKIM, unattended-upgrades отвечайте **N** (оставить вашу версию). Свои настройки вы меняли
  специально, новые значения по умолчанию их сотрут.
- **Перезапуск служб без вопросов** — да.

```bash
sudo reboot
```

После перезагрузки: `cat /etc/os-release` — Debian 13, `systemctl --failed` — посмотреть, что не
поднялось (`azzb` не поднимется, пока не сделан шаг 6 — это ожидаемо).

## 5. PostgreSQL 15 → 17

Debian 13 ставит PostgreSQL 17 и создаёт для него пустой кластер, а данные остаются в
кластере 15, который продолжает работать.

```bash
pg_lsclusters
sudo pg_dropcluster 17 main --stop        # пустой кластер 17, созданный при установке
sudo pg_upgradecluster --method=dump 15 main
pg_lsclusters                             # 17 main — online, порт 5432; 15 main — down
```

`--method=dump` переносит данные через дамп: дольше, зато старый кластер 15 остаётся
нетронутым до тех пор, пока вы его не удалите, — к нему можно вернуться. Нужно свободное место
размером с базу.

Проверить, что данные на месте:

```bash
sudo -u postgres psql -d azzb -c "SELECT count(*) FROM post_post;"
sudo -u postgres psql -d azzb -c "SELECT extname FROM pg_extension;"     # есть pg_trgm
```

Старый кластер удалить после того, как сайт заработает (шаг 7):

```bash
sudo pg_dropcluster 15 main
sudo apt purge postgresql-15
```

## 6. Python 3.13: пересоздать окружение

Окружение `venv` собрано под Python 3.11, которого в Debian 13 больше нет, а uWSGI теперь
работает с Python 3.13 — окружение нужно создать заново:

```bash
cd /var/www/azzb
rm -rf venv
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/python manage.py check
venv/bin/python manage.py migrate         # новых миграций нет — должно ответить «No migrations to apply»
sudo systemctl start azzb
```

## 7. nginx 1.26 и проверка

`sudo nginx -t` предупредит, что `listen … http2` устарело. В nginx 1.26 пишется так:

```nginx
listen 443 ssl;
http2 on;
```

```bash
sudo nginx -t && sudo systemctl reload nginx
sudo certbot renew --dry-run
```

Пройдите проверку из [stage3.md](stage3.md), раздел 5, и отправьте тестовое письмо — в Gmail
«Показать оригинал» должно показать `SPF: PASS`, `DKIM: PASS`.

Напоследок:

```bash
sudo apt autoremove
systemctl --failed
```

## Если что-то пошло не так

- **Сайт не запускается** — `sudo journalctl -u azzb -n 50 --no-pager`. Чаще всего это
  окружение (шаг 6) или путь к Python в настройках uWSGI.
- **База** — пока не удалён кластер 15, можно вернуться к нему: `sudo pg_ctlcluster 17 main stop`,
  `sudo pg_ctlcluster 15 main start` (порт у него будет другой — `pg_lsclusters`; поправьте
  `POSTGRES_PORT` в `.env`).
- **Система не загружается** — консоль VNC в панели FirstVDS. Если не починить — переустановка
  Debian 13 из панели и восстановление из архива шага 2: пакеты по `packages.txt`, настройки из
  `etc.tgz`, база — `pg_restore`, затем шаги 5–7.

## Потом: память

Сейчас 1 ГБ памяти, и сервер уже использует 440 МБ подкачки. Для этапа 4 (Redis и отдельный
процесс для WebSocket) этого мало — перед ним стоит перейти на тариф с 2 ГБ.
