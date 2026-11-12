# Наведение порядка в проекте

_Начат 2026-11-10. Здесь техдолг и рефакторинг; новые фичи — в [ROADMAP.md](ROADMAP.md)._

Цель: редактор и CI не ругаются, у каждой вещи одно понятное место, CSS держится на токенах.
Шаги идут по порядку: каждый следующий проще делать, когда сделан предыдущий.

---

## Сделано 2026-11-10

| Что | Где |
|---|---|
| ruff и pyright настроены: табы, кавычки не трогаем, правила `E4 E7 E9 F I DJ B UP` | `pyproject.toml` |
| Типы Django для редактора: `django-stubs`, `djangorestframework-stubs`; ruff и basedpyright — в dev-зависимостях | `requirements-dev.txt` |
| `Profile.objects` и `Post.objects` знают свои методы (`public`, `visible_to`, `for_feed`…); у моделей объявлены поля `*_id` и обратные связи (`user.profile`, `post.images`) | `accounts/models.py`, `post/models.py`, `moderation/models.py` |
| Тесты берут модель пользователя напрямую, а не через `get_user_model()`, поэтому редактор знает `create_user` | `*/tests.py` (кроме `post/tests.py`, см. шаг 1) |
| `import customUser.signals` → `from . import signals  # noqa: F401` с пояснением | `accounts/apps.py` |
| `verbose_name` у приложений `azzb`, `api` и у моделей `Profile`, `FollowThrough`, `Post`, `RateCounter` (миграции только меняют `Meta`, SQL не выполняют) | `*/apps.py`, миграции `0004`/`0012` |
| Неподтверждённые регистрации скрыты везде через одну точку `Profile.objects.public()`: «Кого почитать», страница профиля (404), списки и счётчики подписок, API | `accounts/models.py` |
| Выпадающие меню открываются в верхнем слое (Popover API): их больше не обрезает `overflow` и не перекрывает `z-index` родителей. Позицию считает скрипт: меню переворачивается, если не помещается, и прижимается к краям экрана | `azzb.js` («Меню»), `azzb.css` |
| Меню «…» профиля раскрывается вправо (`.menu-start`) и на телефоне, и на десктопе | `accounts/profile.html` |
| `/.well-known/appspecific/com.chrome.devtools.json` при `DEBUG`: Chrome DevTools связывают сайт с папкой проекта (Workspaces), 404 в логе пропали | `azzb/views.py` |

После этого pyright показывает 57 ошибок вместо 121. `ruff check` чист везде, кроме `post/` (11 замечаний): там шла параллельная работа, его доводит шаг 1.

---

## Шаг 1. Единый стиль кода — S

1. Дождаться, пока в рабочей копии не останется чужих незакоммиченных правок (ветка «длинные ветки постов»).
2. Одним отдельным коммитом, без других изменений:
   ```
   .venv/Scripts/ruff check --fix .
   .venv/Scripts/ruff format .
   ```
   Хеш этого коммита записать в `.git-blame-ignore-revs`, чтобы `git blame` его пропускал.
3. Добавить в `.github/workflows/tests.yml` шаги `ruff check .` и `ruff format --check .`.
4. В Zed включить форматирование при сохранении: ruff возьмёт настройки из `pyproject.toml`. Без них он
   переводил файлы на 4 пробела, поэтому `apps.py` раньше расходились с остальным кодом.

## Шаг 2. Остаток ошибок типов — S

Осталось 57, почти все одного вида:

| Ошибок | Что | Как чинить |
|---|---|---|
| ~45 | `request.user.profile`: у `request.user` тип «пользователь или аноним» | Класс `AuthedRequest(HttpRequest)` с `user: CustomUser` в `azzb/typing.py`, аннотировать им вьюхи под `login_required` |
| 4 | `PIL.Image.LANCZOS` | `Image.Resampling.LANCZOS` |
| 5 | `get_reason_display()` и др. pyright не видит | `Reason(report.reason).label` или аннотация метода |
| 3 | `Meta` у сериализаторов DRF | Ложное срабатывание стабов: `# pyright: ignore[reportIncompatibleVariableOverride]` на строке (или уйдёт вместе с API, шаг 4) |
| остальное | `post/tests.py` (`get_user_model`), «possibly unbound» в тестах, `moderation/forms.py` (`cleaned_data` может быть `None`) | Точечно |

После этого добавить в CI `basedpyright` с `typeCheckingMode = "standard"`.

## Шаг 3. Разобрать `customUser` — ✅ сделано 2026-11-10

**Что было не так.** Имя не по PEP 8, общие для всего сайта шаблонные теги лежали в пакете аккаунтов,
а страница профиля называлась `registration/profile.html`, хотя к регистрации отношения не имеет.

**Что сделано.** Переименован только Python-пакет. Метку приложения (`app_label`) не трогали: по ней
Django называет таблицы, ведёт историю миграций и находит модель пользователя
(`AUTH_USER_MODEL = 'customUser.CustomUser'`). На неё же ссылаются allauth и журнал админки.

```python
# accounts/apps.py
class AccountsConfig(AppConfig):
	name = 'accounts'
	label = 'customUser'   # таблицы, миграции и AUTH_USER_MODEL остаются как были
```

| Было | Стало |
|---|---|
| `customUser/` | `accounts/`, в коде `from accounts.models import …` |
| `customUser/templatetags/azzb_ui.py` | `azzb/templatetags/azzb_ui.py` (`{% load azzb_ui %}` не изменился) |
| `customUser/templatetags/show_posts.py` | `post/templatetags/show_posts.py` (рендерит `post/post.html`) |
| `registration/profile.html` | `accounts/profile.html` |
| `registration/edit.html` | `accounts/profile_edit.html` |
| `registration/account.html` | `accounts/account_settings.html` |
| `registration/blocked.html` | `accounts/blocked.html` |
| `registration/includes/relation_row.html` | `accounts/includes/relation_row.html` |
| `registration/auth_base.html` | `azzb/card_base.html` (страницы 404/429/500 и экран бана) |

Что осталось с меткой `customUser` и так и должно остаться: `AUTH_USER_MODEL`, адреса админки
`/admin/customUser/…`, зависимости миграций `('customUser', '00xx_…')`, команды вроде
`manage.py migrate customUser` и `sqlsequencereset customUser`. В старых миграциях поменялись только
пути импорта (`accounts.models.UsernameValidator` и др.): Django сравнивает операции, а не пути.

**Деплой.** Схема базы не меняется (только миграция `0012` с `verbose_name`). Если код заливается
через `scp`, а не `git pull`, на сервере нужно удалить старую папку `/var/www/azzb/customUser`
(см. SERVER_CHEATSHEET.md, раздел 4.2). Сама она ничего не сломает, но будет путать.

**Потом, если понадобится.** Подписки, блокировки и заглушение (`FollowThrough`, `Block`, `Mute`,
`relations.py`) можно вынести в отдельное приложение `social`. Метку `customUser` два приложения
делить не могут, поэтому это перенос моделей между приложениями: `db_table` оставить прежним и
перенести модели миграциями `SeparateDatabaseAndState` (в базе ничего не меняется, меняется только
состояние Django). Делать стоит, только если `accounts` снова разрастётся.

## Шаг 4. Убрать старый API — S

`azzb/serializers.py` уже сейчас мёртвый: импортирует из `azzb.models` модели, которых там нет.
Шаблоны и `azzb.js` к `/api/new-post/`, `/api/like-post/`, `/api/delete-post/`, `/api/edit-post/`,
`/api/profiles/` больше не обращаются: всё идёт через HTMX-вьюхи `post/views.py`. Если внешних
клиентов нет, приложение `api` и `rest_framework` можно убрать вместе с тестами. Если API нужен для
будущего мобильного приложения (раздел H дорожной карты), лучше спроектировать его заново, а не
поддерживать этот.

## Шаг 5. CSS и JS: сборка и компоненты — M

**Решено:** без Tailwind и без SPA. Свои токены остаются, CSS и JS разбиты на файлы в `frontend/`
и собираются esbuild (`docs/frontend.md`). Дальше:
1. Компоненты шаблонов — django-cotton (`docs/frontend.md`). Подключён вместе с ревизией R2:
   есть `<c-empty>`, следующие — вкладки, призыв войти; вместо `{% include %}` с `{% with %}`
   и вместо `style="…"` в шаблонах.
2. htmx-расширение idiomorph: обновление карточек без потери фокуса и прокрутки, тогда
   ручные `replaceCardBodies`/`insertCards` в `frontend/js/composer.js` упрощаются.
3. htmx — из npm в общую сборку вместо `azzb/static/vendor/`.

## Мелочи

- `/.well-known/security.txt` на проде: адрес `SUPPORT_EMAIL` для сообщений об уязвимостях. Проще всего отдавать статикой через nginx.
- `notes.txt`, `access.txt` в корне: проверить, нужны ли они в git.
- `azzb/settings_sqlite.py`: удалить после переезда на PostgreSQL (так написано в нём самом).
- `CORS_ALLOWED_ORIGINS` с `localhost:3000` и `django-cors-headers`: остались от старого фронтенда, проверить, нужны ли они.
