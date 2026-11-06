# Этап 2: что настроить на сервере перед выкладкой

Код этапа 2 (подтверждение почты, лимиты, капча, блокировки, жалобы) почти не требует
ручной настройки: таблицы, включая кэш, создаёт `python manage.py migrate`. Остаётся то,
что живёт вне репозитория.

## 1. Почта

Без работающей почты новые пользователи не смогут подтвердить адрес и войти. Сначала —
[mail.md](mail.md). Аккаунты, заведённые до allauth, миграция `customUser.0007` помечает
подтверждёнными, их это не затронет.

## 2. Настоящий IP посетителя для лимитов

Лимиты на вход, регистрацию и сброс пароля считаются по IP. За nginx Django видит
`127.0.0.1` у всех посетителей сразу — без этой настройки лимит «5 регистраций в час с одного
IP» сработал бы на весь сайт. В `location /` (где `proxy_pass` на gunicorn):

```nginx
proxy_set_header X-Real-IP $remote_addr;
```

Именно `proxy_set_header`: nginx **перезаписывает** заголовок, и посетитель не сможет
подставить свой. Django читает его по умолчанию (`CLIENT_IP_HEADER=X-Real-IP`).

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
