#!/bin/sh
# Backup tools are installed in the image; failed snapshots never count as complete.
set -eu
case "${1:-once}" in
  once) exec python3 /backup.py once ;;
  verify) exec python3 /backup.py verify "${2:?completed backup directory required}" ;;
  daemon)
    while :; do
      python3 /backup.py once || echo '[backup] failed; last complete backup retained' >&2
      delay=$(python3 -c 'from datetime import datetime,timedelta,timezone; n=datetime.now(timezone.utc); t=n.replace(hour=3,minute=0,second=0,microsecond=0); t=t if t>n else t+timedelta(days=1); print(max(1,int((t-n).total_seconds())))')
      sleep "$delay"
    done
    ;;
  restore)
    stamp="${2:?backup stamp required}"
    case "$stamp" in *[!A-Za-z0-9-]*|'') echo 'Invalid backup stamp' >&2; exit 2 ;; esac
    python3 /backup.py verify "${BACKUP_DIR:-/backups}/$stamp"
    cat <<INSTRUCTIONS
Backup $stamp verified. Restore only into fresh, isolated volumes/database.
Copy the complete backup directory off-host and verify its checksums there.
Restore users.dump with pg_restore into a NEW PostgreSQL 16 database, then
extract sqlite.tar.gz and data.tar.gz into a NEW application data volume.
See docs/milestone-0-operations.md for the executable owned scratch drill.
This restore subcommand only verifies and prints instructions; it restores nothing.
Do not extract over an active pilot volume. Database migrations are not
reversed by changing images; use the matching pre-upgrade data snapshot.
INSTRUCTIONS
    ;;
  *) echo 'Usage: backup.sh once|daemon|verify DIRECTORY|restore STAMP' >&2; exit 2 ;;
esac
