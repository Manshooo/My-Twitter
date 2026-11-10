import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')

def env(name, default=''):
	"""Переменная окружения; пустая строка (`EMAIL_HOST=` в .env) считается незаданной."""
	value = os.getenv(name, '').strip()
	return value or default


def env_bool(name, default=False):
	value = env(name)
	return value.lower() in ('1', 'true', 'yes', 'on') if value else default


# os.getenv возвращает строку, и раньше даже DJANGO_DEBUG=False включало отладку.
DEBUG = env_bool('DJANGO_DEBUG')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

INSTALLED_APPS = [
	'django.contrib.admin',
	'django.contrib.auth',
	'django.contrib.contenttypes',
	'django.contrib.sessions',
	'django.contrib.messages',
	'django.contrib.staticfiles',
	# Полнотекстовый поиск и триграммы (D3).
	'django.contrib.postgres',

	'api',
	'azzb',
	'post',
	'accounts',
	'moderation',
	'notifications',

	# Регистрация с подтверждением почты, вход, сброс и смена пароля и почты (E1).
	'allauth',
	'allauth.account',

	'rest_framework',
	'corsheaders',
]

MIDDLEWARE = [
	'django.middleware.security.SecurityMiddleware',
	'django.contrib.sessions.middleware.SessionMiddleware',
	'corsheaders.middleware.CorsMiddleware',
	'django.middleware.common.CommonMiddleware',
	'django.middleware.csrf.CsrfViewMiddleware',
	'django.contrib.auth.middleware.AuthenticationMiddleware',
	'django.contrib.messages.middleware.MessageMiddleware',
	'django.middleware.clickjacking.XFrameOptionsMiddleware',
	'allauth.account.middleware.AccountMiddleware',
	# Забаненным — экран «Аккаунт заблокирован» вместо страниц (E4).
	'moderation.middleware.BanMiddleware',
	'accounts.middleware.SetLastVisitMiddleware',
	'azzb.htmx.HtmxVaryMiddleware',
]

# Debug toolbar нужен только при разработке: на проде пакет можно даже не ставить.
if DEBUG:
	INSTALLED_APPS += ['debug_toolbar']
	MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')

CORS_ORIGIN_ALLOW_ALL = False
CORS_ALLOWED_ORIGINS = [
       'https://localhost:3000',
	   'http://localhost:3000',
]

INTERNAL_IPS = ['127.0.0.1',]

REST_FRAMEWORK = {
	'DEFAULT_RENDERER_CLASSES': [
		'rest_framework.renderers.JSONRenderer',
	],
	# BasicAuthentication убрана: она позволяла перебирать пароли через API без лимитов.
	'DEFAULT_AUTHENTICATION_CLASSES': [
		'rest_framework.authentication.SessionAuthentication',
	],
	# Без этого DRF по умолчанию использует AllowAny — любой аноним мог менять и удалять профили.
	'DEFAULT_PERMISSION_CLASSES': [
		'rest_framework.permissions.IsAuthenticated',
	],
}
ALLOWED_HOSTS = [
	'localhost',
	'127.0.0.1',
	'azzb.ru',
	'www.azzb.ru'
]

ROOT_URLCONF = 'azzb.urls'

TEMPLATES = [
	{
		'BACKEND': 'django.template.backends.django.DjangoTemplates',
		'DIRS': [
			'azzb/templates'
		],
		'APP_DIRS': True,
		'OPTIONS': {
			'context_processors': [
				'django.template.context_processors.debug',
				'django.template.context_processors.request',
				'django.contrib.auth.context_processors.auth',
				'django.contrib.messages.context_processors.messages',
				'azzb.context_processors.ui',
			],
		},
	},
]

WSGI_APPLICATION = 'azzb.wsgi.application'

# Только PostgreSQL — и на проде, и локально, и в CI. Параметры — переменные POSTGRES_*
# (см. .env.example). Для разового дампа старой SQLite-базы есть azzb/settings_sqlite.py.
if not os.getenv('POSTGRES_DB'):
	raise ImproperlyConfigured(
		'Не задан POSTGRES_DB. Пропишите POSTGRES_* в .env (образец — .env.example).'
	)

DATABASES = {
	'default': {
		'ENGINE': 'django.db.backends.postgresql',
		'NAME': os.getenv('POSTGRES_DB'),
		'USER': os.getenv('POSTGRES_USER', ''),
		'PASSWORD': os.getenv('POSTGRES_PASSWORD', ''),
		'HOST': os.getenv('POSTGRES_HOST', 'localhost'),
		'PORT': os.getenv('POSTGRES_PORT', '5432'),
		# Держим соединение между запросами, но проверяем, что оно живо.
		'CONN_MAX_AGE': int(os.getenv('POSTGRES_CONN_MAX_AGE', '60')),
		'CONN_HEALTH_CHECKS': True,
	}
}


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
	{
		'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
	},
	{
		'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
	},
	{
		'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
	},
	{
		'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
	},
]

AUTH_USER_MODEL = 'customUser.CustomUser'
LOGIN_URL = 'account_login'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

AUTHENTICATION_BACKENDS = [
	# Вход в /admin/ по логину и паролю.
	'django.contrib.auth.backends.ModelBackend',
	# Вход на сайт: по логину или почте, с проверкой подтверждения почты.
	'allauth.account.auth_backends.AuthenticationBackend',
]

# ---------- django-allauth (E1) ----------
ACCOUNT_ADAPTER = 'accounts.adapter.AccountAdapter'
ACCOUNT_FORMS = {
	'login': 'accounts.forms.LoginForm',
	'signup': 'accounts.forms.SignupForm',
}
ACCOUNT_LOGIN_METHODS = {'username', 'email'}
ACCOUNT_SIGNUP_FIELDS = ['username*', 'email*', 'password1*', 'password2*']
# Без подтверждённой почты войти нельзя: так боты не наплодят аккаунтов на чужие адреса.
ACCOUNT_EMAIL_VERIFICATION = 'mandatory'
ACCOUNT_UNIQUE_EMAIL = True
# Одна почта на аккаунт; смена — через подтверждение нового адреса, старый работает до него.
ACCOUNT_CHANGE_EMAIL = True
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_LOGIN_ON_PASSWORD_RESET = True
# Сессия живёт SESSION_COOKIE_AGE (2 недели) без галочки «Запомнить меня» — как было до allauth.
ACCOUNT_SESSION_REMEMBER = True
ACCOUNT_LOGOUT_REDIRECT_URL = '/'
ACCOUNT_EMAIL_SUBJECT_PREFIX = 'AzzB: '
ACCOUNT_DEFAULT_HTTP_PROTOCOL = 'http' if DEBUG else 'https'
# Логин занимает адрес /users/<логин>/ и может совпасть со служебными словами в ссылках и письмах.
# Лимиты allauth (E2). Ключ «ip» — адрес из CLIENT_IP_HEADER (см. AccountAdapter.get_client_ip),
# «key» — логин или почта из формы, «user» — пользователь.
ACCOUNT_RATE_LIMITS = {
	'login': '30/m/ip',
	# Перебор паролей: 10 неудач в минуту с одного IP и 5 за 5 минут на один аккаунт.
	'login_failed': '10/m/ip,5/5m/key',
	'signup': '5/h/ip,20/d/ip',
	'reset_password': '10/m/ip,3/h/key',
	'reset_password_from_key': '20/m/ip',
	'confirm_email': '1/3m/key',
	'change_password': '5/m/user',
	'manage_email': '10/m/user',
}
ACCOUNT_USERNAME_BLACKLIST = [
	'admin', 'administrator', 'root', 'api', 'auth', 'azzb', 'help', 'support', 'moderator',
	'moderation', 'noreply', 'no-reply', 'postmaster', 'abuse', 'security', 'settings', 'static',
	'media', 'staff', 'system', 'users', 'www',
]

LANGUAGE_CODE = 'ru'

TIME_ZONE = 'Europe/Moscow'

USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'static'
#STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
# Кэш в PostgreSQL: общий для всех воркеров, на нём держатся лимиты allauth (E2).
# Таблицу создаёт миграция azzb/migrations/0001_cache_table.py. Когда появится Redis (этап 4),
# достаточно поменять BACKEND и LOCATION.
CACHES = {
	'default': {
		'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
		'LOCATION': 'azzb_cache',
	},
}

# Лимиты частоты (E2). За nginx настоящий IP посетителя приходит в заголовке, который nginx
# ставит сам: proxy_set_header X-Real-IP $remote_addr; (docs/deploy/security.md).
CLIENT_IP_HEADER = env('CLIENT_IP_HEADER', '' if DEBUG else 'X-Real-IP')

# Капча на регистрации — Yandex SmartCaptcha (E2). Без ключей выключена (разработка, тесты).
SMARTCAPTCHA_CLIENT_KEY = env('SMARTCAPTCHA_CLIENT_KEY')
SMARTCAPTCHA_SERVER_KEY = env('SMARTCAPTCHA_SERVER_KEY')

# Куда писать людям: апелляции на бан, вопросы по персональным данным (правила и политика, C5).
# Ящик должен реально читаться — Postfix на сервере только отправляет (docs/deploy/mail.md).
SUPPORT_EMAIL = env('SUPPORT_EMAIL', 'support@azzb.ru')
# Номер счётчика Яндекс Метрики. Пусто — Метрика выключена; включается только с согласия посетителя.
YANDEX_METRIKA_ID = env('YANDEX_METRIKA_ID', '')

# Правила и политика конфиденциальности (C5, E6). Оператор персональных данных — тот, кто
# отвечает за сайт по 152-ФЗ: ФИО (для физлица) или наименование ИП/организации.
LEGAL_OPERATOR = env('LEGAL_OPERATOR', '[ФИО или наименование оператора — задайте LEGAL_OPERATOR в .env]')

# Почта (E0). На проде письма уходят через Postfix на этом же сервере (localhost:25, без пароля),
# он подписывает их DKIM-ключом azzb.ru — см. docs/deploy/mail.md. Всё переопределяется из .env,
# например, чтобы временно слать через внешний SMTP. При разработке письма печатаются в консоль.
EMAIL_BACKEND = env(
	'EMAIL_BACKEND',
	'django.core.mail.backends.console.EmailBackend' if DEBUG else 'django.core.mail.backends.smtp.EmailBackend',
)
EMAIL_HOST = env('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(env('EMAIL_PORT', '25'))
EMAIL_HOST_USER = env('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS')
EMAIL_USE_SSL = env_bool('EMAIL_USE_SSL')
# Без таймаута зависший SMTP держал бы воркер, пока пользователь ждёт ответа на «Сбросить пароль».
EMAIL_TIMEOUT = int(env('EMAIL_TIMEOUT', '10'))
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', 'AzzB <noreply@azzb.ru>')
SERVER_EMAIL = env('SERVER_EMAIL', DEFAULT_FROM_EMAIL)

# Ошибки (в том числе сбои отправки писем) пишем в stderr — их собирает journald (`journalctl -u azzb`).
# Без этого при DEBUG=False Django отправлял бы их только письмом админам, которых нет.
LOGGING = {
	'version': 1,
	'disable_existing_loggers': False,
	'handlers': {
		'console': {'class': 'logging.StreamHandler'},
	},
	'root': {'handlers': ['console'], 'level': 'WARNING'},
	'loggers': {
		'azzb': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
	},
}
