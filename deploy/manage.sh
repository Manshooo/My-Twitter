#!/usr/bin/env bash
# manage.py в той версии образа, что сейчас выложена (A10): /srv/azzb/manage.sh purge_expired
# Для cron и ручных команд (createsuperuser, shell, sendtestemail).
set -euo pipefail
cd "${AZZB_DIR:-/srv/azzb}"
AZZB_TAG=$(cat .deployed-tag) exec docker compose -f docker-compose.prod.yml run --rm --no-deps web python manage.py "$@"
