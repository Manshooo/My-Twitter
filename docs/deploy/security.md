# Этап 2: что настроить на сервере перед выкладкой

Код этапа 2 (подтверждение почты, лимиты, капча, блокировки, жалобы) почти не требует
ручной настройки: таблицы, включая кэш, создаёт `python manage.py migrate`. Остаётся то,
что живёт вне репозитория.

## 1. Почта

Без работающей почты новые пользователи не смогут подтвердить адрес и войти. Сначала —
[mail.md](mail.md). Аккаунты, заведённые до allauth, миграция `customUser.0007` помечает
подтверждёнными, их это не затронет.

## 2. Настоящий IP посетителя для лимитов

Лимиты на вход, регистрацию, сброс пароля, посты и поиск считаются по IP. На проде Django
сначала смотрит заголовок `X-Real-IP` (`CLIENT_IP_HEADER`), поэтому его обязательно должен
**ставить сам nginx** — иначе посетитель пришлёт свой и обойдёт лимиты, а без заголовка за
прокси все посетители выглядели бы как `127.0.0.1`.

В `location /` сайта — в зависимости от того, как nginx передаёт запросы приложению.

uWSGI по своему протоколу (`uwsgi_pass`, так на проде):

```nginx
include uwsgi_params;
uwsgi_param HTTP_X_REAL_IP $remote_addr;
```

HTTP-прокси (`proxy_pass`, например на gunicorn или uvicorn):

```nginx
proxy_set_header X-Real-IP $remote_addr;
```

В обоих случаях nginx **перезаписывает** значение, присланное посетителем.

Проверить: войти на сайт, открыть админку → «Журнал действий» — у записи о входе должен быть
ваш настоящий IP, а не `127.0.0.1`.

```bash
nginx -t && systemctl reload nginx
```

## 3. Капча Yandex SmartCaptcha

1. Консоль Yandex Cloud → SmartCaptcha → «Создать капчу». Домен — `azzb.ru`,
   сложность — «Простая» (лимиты и подтверждение почты дополняют её).
2. Ключи клиента и сервера — в `.env` на сервере:

   ```ini
   SMARTCAPTCHA_CLIENT_KEY=ysc1_...
   SMARTCAPTCHA_SERVER_KEY=ysc2_...
   ```
3. `systemctl restart azzb`, открыть `/auth/signup/` — под формой появится «Я не робот».

Без ключей капча выключена, остальное работает.

## 4. Выкладка

```bash
pip install -r requirements.txt     # добавился django-allauth
python manage.py migrate
python manage.py collectstatic --noinput
systemctl restart azzb
```

Старые адреса входа сменились: `/auth/password_reset/` → `/auth/password/reset/`.
Ссылки из писем сброса пароля, отправленных до выкладки, перестанут работать —
пароль можно запросить заново.

## 5. HTTPS: перенаправление и HSTS

`manage.py check --deploy` предупреждает про `security.W008` (перенаправление на HTTPS) и
`security.W004` (HSTS). Оба делает nginx, а не Django: nginx принимает HTTPS и знает, по какому
протоколу пришёл запрос. Предупреждения после этого остаются — Django не видит настроек nginx.

**HSTS** (`Strict-Transport-Security`) — браузер запоминает, что сайт открывается только по HTTPS:
сам меняет `http://` на `https://` и не даёт пройти мимо ошибки сертификата. Отменить это для
тех, кто уже получил заголовок, нельзя, пока не истечёт `max-age`. Поэтому включаем по шагам.

### Перед включением

1. Перенаправление с HTTP уже работает:

   ```bash
   curl -sI http://azzb.ru | head -3      # 301, Location: https://azzb.ru/
   ```
2. Сертификат продлевается сам — иначе после его истечения сайт не откроется вообще:

   ```bash
   systemctl list-timers | grep -i certbot
   sudo certbot renew --dry-run
   ```
3. На страницах нет ресурсов по `http://` (все внешние — Google Fonts, Метрика, SmartCaptcha — по HTTPS).

### Включение

В `server { listen 443 ssl; … }` сайта:

```nginx
add_header Strict-Transport-Security "max-age=300" always;
```

**Ловушка nginx:** `add_header` из `server` не наследуется в `location`, где есть свой `add_header`.
У `location /media/` они есть (`media.md`) — повторите строку и там, иначе картинки придут без
заголовка. То же для любого другого `location` с `add_header`.

```bash
sudo nginx -t && sudo systemctl reload nginx
curl -sI https://azzb.ru | grep -i strict-transport
curl -sI https://azzb.ru/static/css/azzb.css | grep -i strict-transport
```

### Увеличение срока

| Когда | `max-age` | Сколько |
|---|---|---|
| Сразу | `300` | 5 минут: ошибка в настройке быстро «забудется» |
| Через день без проблем | `604800` | Неделя |
| Ещё через неделю | `31536000` | Год — итоговое значение |

`includeSubDomains` не добавляйте, пока каждый поддомен (`www`, `mail` и другие, если есть в DNS)
не отвечает по HTTPS с действующим сертификатом. `preload` (вшивание домена в браузеры) не нужен:
его почти невозможно отменить.

Если что-то пошло не так — поставьте `max-age=0`: браузеры забудут правило при следующем заходе.

## 6. Python-зависимости на сервере

`pip install -r requirements.txt` ставит недостающее и меняет версии закреплённых пакетов, но
**не удаляет** лишнее и не трогает то, что поставлено руками. За годы в окружении копятся старые
пакеты с уязвимостями. Проверить, что стоит на сервере:

```bash
venv/bin/pip install pip-audit
venv/bin/pip-audit
```

Окружение проще пересоздать начисто, чем чистить. uWSGI стоит не в окружении, а в системе
(пакет Debian), поэтому окружение меняется без пересборки uWSGI. Простой — секунды на перезапуск:

```bash
cd /var/www/azzb
python3 -m venv venv.new
venv.new/bin/pip install -r requirements.txt
venv.new/bin/python manage.py check        # с новым окружением всё импортируется
mv venv venv.old && mv venv.new venv
sudo systemctl restart azzb
```

Проверить сайт; если что-то не так — `mv venv venv.new && mv venv.old venv` и снова
`restart`. Когда всё работает — `rm -rf venv.old`.

В CI (`.github/workflows/tests.yml`) `pip-audit` проверяет `requirements.txt` при каждом пуше:
если для закреплённой версии опубликуют уязвимость, CI станет красным.
