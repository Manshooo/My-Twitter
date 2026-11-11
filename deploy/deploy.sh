#!/usr/bin/env bash
# Выкладка AzzB (A10): копия базы → образ → миграции → перезапуск → проверка.
# Запускает deploy-джоба CI (с SHA коммита) или вы вручную: /srv/azzb/deploy.sh [тег]
# Тег — SHA коммита из ghcr.io/manshooo/my-twitter; без тега — latest. Подробно — docs/deploy/docker.md.
set -euo pipefail

DIR=${AZZB_DIR:-/srv/azzb}
TAG=${1:-latest}
cd "$DIR"
export AZZB_TAG=$TAG
compose() { docker compose -f docker-compose.prod.yml "$@"; }
PREVIOUS=$(cat .deployed-tag 2>/dev/null || true)

on_error() {
	echo
	echo "!! Выкладка $TAG не удалась. Сайт работает на том, что успело запуститься."
	if [ -n "$PREVIOUS" ]; then
		echo "   Вернуть прошлую версию:  $DIR/deploy.sh $PREVIOUS"
	fi
	echo "   Если сломали миграции — база до выкладки: $DUMP"
	echo "   (pg_restore --clean --if-exists -h localhost -U azzb -d azzb $DUMP, сайт на это время остановить)"
	echo "   Журнал: journalctl -t azzb-web -t azzb-ws -t azzb-redis -n 100 --no-pager"
}
DUMP="(не сделана)"
trap on_error ERR

echo "== 1/5 Копия базы"
mkdir -p backups
DUMP="$DIR/backups/predeploy-$(date +%F-%H%M)-${TAG:0:12}.dump"
# Пароль — из ~/.pgpass (docs/deploy/docker.md, шаг 3).
pg_dump --format=custom -h localhost -U "${PGUSER:-azzb}" "${PGDATABASE:-azzb}" > "$DUMP"
# Хранятся три последние: ночные копии — отдельно (backup.sh).
ls -1t backups/predeploy-*.dump | tail -n +4 | xargs -r rm --

echo "== 2/5 Образы $TAG"
compose pull

echo "== 3/5 Миграции"
compose run --rm --no-deps web python manage.py migrate --noinput

echo "== 4/5 Перезапуск"
# web, а с COMPOSE_PROFILES=realtime в .env — ещё ws и redis (F1). Redis перезапускается, только если сменился образ.
compose up -d --remove-orphans --wait --wait-timeout 90

echo "== 5/5 Проверка"
curl -fsS --retry 10 --retry-delay 3 --retry-all-errors -H 'Host: azzb.ru' http://127.0.0.1:8001/healthz
echo
if [ -n "$(compose ps -q ws)" ]; then
	curl -fsS --retry 10 --retry-delay 3 --retry-all-errors -H 'Host: azzb.ru' http://127.0.0.1:8002/healthz
	echo
fi
echo "$TAG" > .deployed-tag
docker image prune -f > /dev/null
echo "Готово: $TAG (было: ${PREVIOUS:-—})"
