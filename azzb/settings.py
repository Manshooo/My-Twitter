from pathlib import Path
import os

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv
load_dotenv()
BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')

# os.getenv возвращает строку, и раньше даже DJANGO_DEBUG=False включало отладку.
DEBUG = os.getenv('DJANGO_DEBUG', '').strip().lower() in ('1', 'true', 'yes', 'on')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

INSTALLED_APPS = [
	'django.contrib.admin',
	'django.contrib.auth',
	'django.contrib.contenttypes',
	'django.contrib.sessions',
	'django.contrib.messages',
	'django.contrib.staticfiles',

	'api',
	'azzb',
	'post',
	'customUser',

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
	'customUser.middleware.SetLastVisitMiddleware',
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
LOGIN_URL = '/auth/login'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

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
#EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

EMAIL_HOST = 'smtp.mail.ru'
EMAIL_PORT = 2525
EMAIL_HOST_USER = "information@azzb.ru"
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')
EMAIL_USE_TLS = True
EMAIL_USE_SSL = False
SERVER_EMAIL = EMAIL_HOST_USER
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER