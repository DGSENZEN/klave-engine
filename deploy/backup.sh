#!/bin/sh
# Backs up everything irreplaceable: the users database (accounts, sessions,
# permissions) and all of /data — SQLite bases via an online snapshot, the
# rest as files. Runs in
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
DATA_DIR="${DATA_DIR:-/data}"

# Todo /data, no una lista: una lista se queda corta en cuanto nace un
# archivo nuevo (le faltaban projects_registry.json, bitacora/, sources/,
# share_links.json). Las bases SQLite no se copian «en caliente» con tar: se
# sacan con la copia en línea de SQLite (.backup), consistente aunque la API
# esté escribiendo, y el resto se empaqueta aparte.
ensure_sqlite() {
    command -v sqlite3 >/dev/null 2>&1 && return 0
    apk add --no-cache sqlite >/dev/null 2>&1 || true
    command -v sqlite3 >/dev/null 2>&1
}

snapshot_sqlite() {
    stage="$1"
    found=0
    for db in $(cd "$DATA_DIR" && find . -type f -name '*.db' 2>/dev/null); do
        found=$((found + 1))
        mkdir -p "$stage/$(dirname "$db")"
        if [ "$HAVE_SQLITE" = 1 ]; then
            sqlite3 "$DATA_DIR/$db" ".backup '$stage/$db'"
        else
            # Sin sqlite3: la base con su diario WAL, juntos. Consistente sólo
            # si nadie escribe en ese instante; se avisa.
            cp "$DATA_DIR/$db" "$stage/$db"
            for side in -wal -shm; do
                [ -f "$DATA_DIR/$db$side" ] && cp "$DATA_DIR/$db$side" "$stage/$db$side"
            done
        fi
    done
    echo "[backup]   $found bases SQLite"
}

run_backup() {
    stamp=$(date -u +%Y%m%dT%H%M%S)
    dest="$BACKUP_DIR/$stamp"
    mkdir -p "$dest"
    echo "[backup] $stamp: users database"
    pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -Fc -f "$dest/users.dump"
    echo "[backup] $stamp: bases SQLite (copia en línea)"
    HAVE_SQLITE=0
    if ensure_sqlite; then
        HAVE_SQLITE=1
    else
        echo "[backup]   AVISO: sin sqlite3 en la imagen; las bases se copian con su WAL" \
             "(consistente sólo con la API quieta)"
    fi
    snapshot_sqlite "$dest/sqlite"
    tar -czf "$dest/sqlite.tar.gz" -C "$dest/sqlite" .
    rm -rf "$dest/sqlite"
    echo "[backup] $stamp: el resto de /data"
    list="$dest/.files"
    (cd "$DATA_DIR" && find . -type f ! -name '*.db' ! -name '*.db-wal' ! -name '*.db-shm' \
        ! -name '*.part' > "$list")
    tar -czf "$dest/data.tar.gz" -C "$DATA_DIR" -T "$list"
    echo "[backup]   $(wc -l < "$list" | tr -d ' ') archivos"
    rm -f "$list"
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
  3. Extract $stamp/data.tar.gz, then $stamp/sqlite.tar.gz (the SQLite
     snapshots, which overwrite the live databases), into the klave-data volume:
     docker run --rm -v <project>_klave-data:/data -v <project>_backups:/backups \
       alpine sh -c 'tar -xzf /backups/$stamp/data.tar.gz -C /data && \
                     tar -xzf /backups/$stamp/sqlite.tar.gz -C /data && \
                     find /data -name "*.db-wal" -o -name "*.db-shm" | xargs rm -f'
  4. docker compose -f docker-compose.prod.yml start api web
INSTRUCTIONS
    ;;
once|*)
    run_backup
    ;;
esac
