# Своя почта `noreply@azzb.ru` (E0)

Письма сайта (подтверждение email, сброс пароля) уходят **с самого VPS** через Postfix,
который только отправляет: ящиков, IMAP и приёма писем нет. OpenDKIM подписывает письма
ключом домена, а SPF, DKIM и DMARC в DNS подтверждают почтовым сервисам, что письмо
действительно от azzb.ru. Без этих записей Gmail, Яндекс и Mail.ru кладут письма в спам
или отбрасывают.

Django шлёт на `localhost:25` без пароля — это умолчание в `azzb/settings.py`, в `.env`
ничего про почту прописывать не нужно.

> **Порядок выкладки.** После обновления кода на сервере Django сразу начнёт слать через
> `localhost:25`. Если Postfix ещё не настроен, на время пропишите в `.env` старый SMTP
> (образец — в `.env.example`) или сначала пройдите шаги 0–4.

Команды — для Debian 12, от root (или через `sudo`).

## 0. Заранее: открыт ли исходящий порт 25

Хостеры часто закрывают его по умолчанию от спамеров. Проверить с сервера:

```bash
nc -vz -w 5 gmail-smtp-in.l.google.com 25
nc -vz -w 5 mx.yandex.ru 25
```

`succeeded`/`open` — порт открыт. Таймаут — написать в поддержку FirstVDS: «Прошу открыть
исходящий порт 25 для VPS 62.109.26.178, нужна отправка транзакционных писем сайта
(подтверждение регистрации, сброс пароля), объём — десятки писем в день». Без этого
дальше идти нет смысла.

Заодно проверьте, что IP не в чёрных списках: <https://mxtoolbox.com/blacklists.aspx>
(ввести `62.109.26.178`).

Обратная запись (PTR) уже есть: `62.109.26.178 → azzb.ru`. Проверить:
`dig -x 62.109.26.178 +short`.

## 1. Postfix только на отправку

```bash
apt install postfix mailutils
```

В мастере выбрать **Internet Site**, имя почты — `azzb.ru`. Затем в
`/etc/postfix/main.cf` проверить или поправить:

```ini
myhostname = azzb.ru
mydomain = azzb.ru
myorigin = $mydomain
# Принимаем соединения только с самого сервера: снаружи это не почтовый сервер.
inet_interfaces = loopback-only
inet_protocols = ipv4
mydestination =
# Письма на наш домен тоже отправляем наружу (ящиков у нас нет).
local_transport = error:local delivery is disabled
relayhost =
# Шифровать соединение с получателем, если он умеет (Gmail, Яндекс, Mail.ru — умеют).
smtp_tls_security_level = may
smtp_tls_loglevel = 1
```

`inet_protocols = ipv4` — потому что SPF и PTR настроены только на IPv4-адрес.

```bash
postfix check && systemctl restart postfix
ss -ltnp | grep :25        # должен слушать только 127.0.0.1:25
```

## 2. OpenDKIM

```bash
apt install opendkim opendkim-tools
mkdir -p /etc/opendkim/keys/azzb.ru
opendkim-genkey -b 2048 -d azzb.ru -s mail -D /etc/opendkim/keys/azzb.ru
chown -R opendkim:opendkim /etc/opendkim
chmod 600 /etc/opendkim/keys/azzb.ru/mail.private
```

`/etc/opendkim.conf` — дописать или поправить:

```ini
Mode                    s
Domain                  azzb.ru
Selector                mail
KeyFile                 /etc/opendkim/keys/azzb.ru/mail.private
Canonicalization        relaxed/simple
Socket                  inet:8891@localhost
OversignHeaders         From
```

Подключить к Postfix — в конец `/etc/postfix/main.cf`:

```ini
milter_default_action = accept
milter_protocol = 6
smtpd_milters = inet:localhost:8891
non_smtpd_milters = inet:localhost:8891
```

```bash
systemctl enable --now opendkim
systemctl restart postfix
cat /etc/opendkim/keys/azzb.ru/mail.txt   # это значение DKIM-записи для DNS
```

## 3. DNS (панель FirstVDS → DNS-менеджмент → azzb.ru)

| Тип | Имя | Значение |
|---|---|---|
| TXT | `azzb.ru.` | `v=spf1 ip4:62.109.26.178 -all` |
| TXT | `mail._domainkey.azzb.ru.` | `v=DKIM1; h=sha256; k=rsa; p=…` — из `mail.txt`, **одной строкой** без кавычек и переносов |
| TXT | `_dmarc.azzb.ru.` | `v=DMARC1; p=none; rua=mailto:ВАШ_ЯЩИК; adkim=s; aspf=s` |

- `rua=` — ящик, который вы реально читаете (например, личный Gmail): туда почтовые
  сервисы раз в сутки шлют отчёты, кто и как отправлял письма от azzb.ru.
- Через 2–4 недели, если в отчётах всё проходит DKIM и SPF, ужесточить до
  `p=quarantine`, ещё позже — до `p=reject`.
- **MX `mail.azzb.ru`**: письма на `@azzb.ru` никто не принимает. Если почта на домене
  не нужна — MX удалить (и A-запись `mail`, если она больше ни для чего). Если хочется
  получать ответы и отскоки — заведите ящик в Яндекс 360 / VK WorkSpace для домена и
  поставьте их MX; отправка сайта при этом всё равно идёт с VPS, SPF тогда дополнить
  их `include:` (они подскажут, какой).

Проверить, что записи видны (DNS обновляется до нескольких часов):

```bash
dig TXT azzb.ru +short
dig TXT mail._domainkey.azzb.ru +short
dig TXT _dmarc.azzb.ru +short
opendkim-testkey -d azzb.ru -s mail -vvv    # должно закончиться «key OK»
```

## 4. Проверка

```bash
# Из проекта, в его виртуальном окружении:
python manage.py sendtestemail you@gmail.com you@yandex.ru you@mail.ru
tail -f /var/log/mail.log      # status=sent у каждого получателя; ошибки — здесь же
```

В Gmail у полученного письма: «⋮ → Показать оригинал» — должно быть
`SPF: PASS`, `DKIM: PASS`, `DMARC: PASS`.

Оценка доставляемости: открыть <https://www.mail-tester.com>, отправить письмо на
выданный адрес (`python manage.py sendtestemail адрес@srv1.mail-tester.com`).
Цель — **9/10 и выше**.

## 5. Репутация

- Зарегистрировать домен в [Google Postmaster Tools](https://postmaster.google.com) и
  [Яндекс Постмастере](https://postmaster.yandex.ru) — там видно, попадают ли письма в спам.
- У нового IP нет репутации: первые недели писем должно быть мало (десятки в день).
  Поэтому почту лучше поднять **заранее, до публичного запуска**.

## 6. Ошибки отправки

Если SMTP недоступен, Django пишет ошибку в журнал сервиса (настройка `LOGGING`
в `azzb/settings.py`):

```bash
journalctl -u azzb --since today | grep -i -E "smtp|mail"
```

Таймаут соединения — 10 секунд (`EMAIL_TIMEOUT`), чтобы зависший SMTP не держал воркер.

## 7. Отчёты DMARC и переход на `quarantine`

Почтовые сервисы раз в сутки присылают на адрес из `rua=` XML-отчёт: с каких IP приходили
письма от имени `azzb.ru` и прошли ли они проверки. Смотреть в отчёте поля `source_ip`,
`count` и `policy_evaluated` (`dkim`, `spf`).

| Что видно | Что значит |
|---|---|
| `62.109.26.178`, `dkim pass`, `spf pass` | Наши письма, всё в порядке |
| Чужой IP, `fail`/`fail`, получатель тот же, что у нашего письма в тот же день | Скорее всего, почтовый шлюз получателя переслал или переписал письмо (антиспам-фильтр, пересылка). Не подделка |
| Чужой IP, `fail`/`fail`, получатели незнакомые и писем много | Кто-то рассылает от имени `azzb.ru` — именно от этого защищает `quarantine`/`reject` |

Когда 2–4 недели все письма с нашего IP проходят обе проверки, политику ужесточают
в два шага (TXT `_dmarc.azzb.ru.`):

1. `v=DMARC1; p=quarantine; pct=25; rua=mailto:ВАШ_ЯЩИК; adkim=s; aspf=s` — четверть
   непрошедших писем идёт в спам; через неделю без жалоб — `pct=100`.
2. Ещё через пару недель — `p=reject`: непрошедшие письма не доставляются вовсе.

Письма с самого сайта (подписаны DKIM, отправлены с нашего IP) это не задевает.
