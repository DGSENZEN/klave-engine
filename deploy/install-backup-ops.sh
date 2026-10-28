#!/usr/bin/env bash
# Apply only after operator approval of AWS grants and backup-data destination.
set -Eeuo pipefail
config=${1:?private backup-ops.env path required}
image=${2:?immutable locally built operations image ID required}
[[ "$image" =~ ^sha256:[0-9a-f]{64}$ ]] || { echo 'Immutable image ID required.' >&2; exit 2; }
python3 - "$config" <<'PY'
import re, sys
from pathlib import Path
values = {}
for line in Path(sys.argv[1]).read_text().splitlines():
    if not line.strip() or line.startswith('#'):
        continue
    key, value = line.split('=', 1)
    if key in values:
        raise SystemExit('Duplicate backup operations setting')
    values[key] = value
patterns = {
    'AWS_REGION': r'[a-z]{2}(?:-[a-z]+)+-\d',
    'KLAVE_BACKUP_BUCKET': r'[a-z0-9][a-z0-9-]{1,61}[a-z0-9]',
    'EC2_INSTANCE_ID': r'i-[0-9a-f]{17}',
}
if set(values) != set(patterns) or any(not re.fullmatch(patterns[k], v) for k, v in values.items()):
    raise SystemExit('Invalid backup operations configuration')
PY
sudo -n docker image inspect "$image" > /dev/null
sudo -n docker volume inspect klave_backups > /dev/null
sudo -n install -d -m 700 /etc/klave /var/lib/klave-ops /var/lib/klave-ops/scratch
sudo -n install -m 600 "$config" /etc/klave/backup-ops.env
printf 'KLAVE_BACKUP_OPS_IMAGE=%s\n' "$image" | sudo -n tee -a /etc/klave/backup-ops.env > /dev/null
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
sudo -n install -m 644 "$script_dir/systemd/klave-offsite-backup.service" /etc/systemd/system/
sudo -n install -m 644 "$script_dir/systemd/klave-offsite-backup.timer" /etc/systemd/system/
sudo -n systemctl daemon-reload
sudo -n systemctl enable --now klave-offsite-backup.timer
sudo -n systemctl start klave-offsite-backup.service
sudo -n systemctl status --no-pager klave-offsite-backup.timer
