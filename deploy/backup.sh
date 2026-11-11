#!/usr/bin/env bash
# Ночные копии AzzB (A10): дамп базы, зашифрованный age, и копия бакета с картинками — в бакет копий,
# хранятся 30 дней.
# cron пользователя azzb_user:  30 3 * * * /srv/azzb/backup.sh >> /srv/azzb/backups/backup.log 2>&1
# Настройка (ключ age, rclone, бакеты) и восстановление — docs/deploy/docker.md, разделы 4 и 9.
set -euo pipefail

DIR=${AZZB_DIR:-/srv/azzb}
REMOTE=${AZZB_RCLONE_REMOTE:-selectel}
MEDIA_BUCKET=${AZZB_MEDIA_BUCKET:-azzb-media}
BACKUP_BUCKET=${AZZB_BACKUP_BUCKET:-azzb-backups}
KEEP_DAYS=${AZZB_BACKUP_DAYS:-30}
cd "$DIR"
mkdir -p backups
STAMP=$(date +%F)
FILE="backups/azzb-$STAMP.dump.age"

# Открытый ключ лежит на сервере, закрытый — только у вас: украденную копию не расшифровать.
pg_dump --format=custom -h localhost -U "${PGUSER:-azzb}" "${PGDATABASE:-azzb}" \
	| age --encrypt --recipients-file backup-key.pub > "$FILE.part"
mv "$FILE.part" "$FILE"
rclone copyto "$FILE" "$REMOTE:$BACKUP_BUCKET/db/azzb-$STAMP.dump.age" --s3-no-check-bucket

# Картинки копируются внутри хранилища, без скачивания на сервер. Стёртые сайтом файлы уходят
# в media-deleted/<дата>/ и живут там столько же, сколько дампы.
rclone sync "$REMOTE:$MEDIA_BUCKET" "$REMOTE:$BACKUP_BUCKET/media" \
	--backup-dir "$REMOTE:$BACKUP_BUCKET/media-deleted/$STAMP" --s3-no-check-bucket --fast-list

# Срок копий — по дате в имени, не по времени файла: перенесённая в media-deleted/ картинка
# сохраняет время загрузки и иначе стёрлась бы на следующую же ночь.
CUTOFF=$(date -d "$KEEP_DAYS days ago" +%F)
for name in $(rclone lsf "$REMOTE:$BACKUP_BUCKET/db" 2>/dev/null || true); do
	day=${name#azzb-}
	if [[ "${day:0:10}" < "$CUTOFF" ]]; then
		rclone deletefile "$REMOTE:$BACKUP_BUCKET/db/$name"
	fi
done
for name in $(rclone lsf --dirs-only "$REMOTE:$BACKUP_BUCKET/media-deleted" 2>/dev/null || true); do
	if [[ "${name%/}" < "$CUTOFF" ]]; then
		rclone purge "$REMOTE:$BACKUP_BUCKET/media-deleted/${name%/}"
	fi
done

# На диске — три последних дампа: место нужно сайту, остальные в бакете.
ls -1t backups/azzb-*.dump.age | tail -n +4 | xargs -r rm --
echo "$(date -Is) ok: $FILE, media synced"
