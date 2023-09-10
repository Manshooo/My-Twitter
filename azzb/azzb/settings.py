from pathlib import Path
import os
from dotenv import load_dotenv
load_dotenv()
BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-=#$ntne!31^xsyfm!pa&=mhn_r42t=69ya*f$09&k58bn!hf(g')

DEBUG = bool(os.getenv('DJANGO_DEBUG', True))
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

INSTALLED_APPS = [
	'django.contrib.admin',
	'django.contrib.auth',
	'django.contrib.contenttypes',
	'django.contrib.sessions',
	'django.contrib.messages',
	'django.contrib.staticfiles',
	'azzb',
    'debug_toolbar',
	'customUser.apps.CustomUserConfig',
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
	"debug_toolbar.middleware.DebugToolbarMiddleware",
]

INTERNAL_IPS = ['127.0.0.1', '62.109.26.178',]

REST_FRAMEWORK = {
	'DEFAULT_AUTHENTICATION_CLASSES': [
		'rest_framework.authentication.BasicAuthentication',
		'rest_framework.authentication.SessionAuthentication',
	]
}
ALLOWED_HOSTS = [
	'localhost',
	'127.0.0.1',
	'azzb.ru'
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
			],
		},
	},
]

WSGI_APPLICATION = 'azzb.wsgi.application'

DATABASES = {
	'default': {
		'ENGINE': 'django.db.backends.sqlite3',
		'NAME': BASE_DIR / 'db.sqlite3',
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