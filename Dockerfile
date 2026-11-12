# Образ сайта (A10). Собирает CI после зелёных тестов и кладёт в ghcr.io; на сервере только скачивается.
# Схема и выкладка — docs/deploy/docker.md.
# Та же версия, что в CI (.github/workflows/tests.yml).
# Стадия 1: CSS и JS из frontend/ (esbuild). В итоговый образ попадают только два собранных файла.
FROM node:22-slim AS frontend
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend ./frontend
RUN npm run build

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1 \
	PIP_NO_CACHE_DIR=1 \
	PIP_DISABLE_PIP_VERSION_CHECK=1 \
	DJANGO_STATIC_MANIFEST=1

WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .
COPY --from=frontend /app/azzb/static/css/azzb.css azzb/static/css/
COPY --from=frontend /app/azzb/static/js/azzb.js azzb/static/js/
# Без базы и настоящего ключа: collectstatic их не трогает, а settings.py без POSTGRES_DB не загрузится.
RUN DJANGO_SECRET_KEY=build-only POSTGRES_DB=build python manage.py collectstatic --noinput \
	&& useradd --system --uid 10001 --no-create-home app

# docker-compose.prod.yml запускает от uid владельца .env на сервере; это — запасной вариант.
USER app
EXPOSE 8001
# gthread: пока один поток ждёт S3 или почту, другие отвечают. --max-requests лечит медленные утечки памяти.
CMD ["gunicorn", "azzb.wsgi:application", \
	"--bind", "127.0.0.1:8001", \
	"--worker-class", "gthread", "--workers", "2", "--threads", "4", \
	"--timeout", "30", "--graceful-timeout", "20", \
	"--max-requests", "1000", "--max-requests-jitter", "100", \
	"--no-control-socket"]
