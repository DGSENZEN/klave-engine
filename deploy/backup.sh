#!/bin/sh
# Backs up everything irreplaceable: the users database (accounts, sessions,
# permissions) and /data (uploads, catálogos por taller, defaults). Runs in
# the postgres:16-alpine image, which brings pg_dump and busybox tar.
#
#   backup.sh            one backup now
#   backup.sh daemon     one backup at start, then daily at ~03:00
#   backup.sh restore <stamp>   print restore instructions for that stamp
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
DB_HOST="${DB_HOST:-users-db}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-klave_users}"
DB_NAME="${DB_NAME:-klave_users}"

run_backup() {
    stamp=$(date -u +%Y%m%dT%H%M%S)
    dest="$BACKUP_DIR/$stamp"
    mkdir -p "$dest"
    echo "[backup] $stamp: users database"
    pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -Fc -f "$dest/users.dump"
    echo "[backup] $stamp: /data (uploads, catálogos, defaults)"
    tar -czf "$dest/data.tar.gz" -C /data \
        $(cd /data && ls -d uploads catalogs catalog.db taller_defaults.json demo 2>/dev/null) \
        2>/dev/null || tar -czf "$dest/data.tar.gz" -C /data .
    du -sh "$dest"/* | sed 's/^/[backup]   /'
    find "$BACKUP_DIR" -maxdepth 1 -type d -name '2*' -mtime "+$KEEP_DAYS" \
        -exec rm -rf {} + 2>/dev/null || true
    echo "[backup] $stamp: done (keeping $KEEP_DAYS days)"
}

case "${1:-once}" in
daemon)
    run_backup
    while :; do
        # Sleep until the next 03:00 UTC.
        now=$(date -u +%s)
        target=$(date -u -d "tomorrow 03:00" +%s 2>/dev/null || echo $((now + 86400)))
        sleep $((target - now))
        run_backup
    done
    ;;
restore)
    stamp="${2:?usage: backup.sh restore <stamp>}"
    cat <<INSTRUCTIONS
Restore $stamp — run on the host, with the stack stopped except users-db:
  1. docker compose -f docker-compose.prod.yml stop api web
  2. docker compose -f docker-compose.prod.yml exec -T users-db \
       pg_restore -U $DB_USER -d $DB_NAME --clean --if-exists \
       < backups volume: $stamp/users.dump
  3. Extract $stamp/data.tar.gz into the klave-data volume (overwrites):
     docker run --rm -v <project>_klave-data:/data -v <project>_backups:/backups \
       alpine tar -xzf /backups/$stamp/data.tar.gz -C /data
  4. docker compose -f docker-compose.prod.yml start api web
INSTRUCTIONS
    ;;
once|*)
    run_backup
    ;;
esac
