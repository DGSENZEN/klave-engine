"""Hourly off-host copy plus an independently alarmed CloudWatch heartbeat."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deploy import s3_backup  # noqa: E402


def run_once(backups: Path, bucket: str, state: Path, instance: str) -> int:
    healthy = False
    try:
        candidates = sorted(
            path
            for path in backups.iterdir()
            if re.fullmatch(r"\d{8}T\d{6}-[0-9a-f]{6}", path.name)
            and path.is_dir()
            and not path.is_symlink()
            and (path / "COMPLETE").is_file()
        )
        if not candidates:
            raise ValueError("No complete local backup")
        try:
            previous = json.loads(state.read_text())
        except (OSError, ValueError):
            previous = {}
        last_stamp = (
            previous.get("stamp", "")
            if isinstance(previous, dict)
            and previous.get("bucket") == bucket
            and previous.get("fetched_back") is True
            else ""
        )
        if not isinstance(last_stamp, str):
            last_stamp = ""
        # Copy in order, including snapshots taken immediately before an upgrade.
        # Advance only after each complete verified copy; a failed prefix is retried.
        for candidate in candidates:
            if candidate.name > last_stamp:
                s3_backup.copy_verified(candidate, bucket, state)
        disk = os.statvfs(backups)
        healthy = (
            s3_backup.is_current(state, 36)
            and disk.f_bavail * disk.f_frsize >= 2 * 1024**3
            and disk.f_files > 0
            and disk.f_favail / disk.f_files >= 0.05
        )
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError):
        healthy = False
    try:
        s3_backup._aws(
            [
                "cloudwatch",
                "put-metric-data",
                "--namespace",
                "Klave/M0",
                "--metric-data",
                json.dumps(
                    [
                        {
                            "MetricName": "OffsiteBackupHealthy",
                            "Value": int(healthy),
                            "Unit": "Count",
                            "Dimensions": [{"Name": "InstanceId", "Value": instance}],
                        }
                    ]
                ),
            ]
        )
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        print(
            "Backup heartbeat delivery failed; missing-data alarm must notify operator.",
            file=sys.stderr,
        )
        return 1
    print("Offsite backup health: " + ("OK" if healthy else "FAILED"))
    return 0 if healthy else 1


if __name__ == "__main__":
    bucket = os.environ.get("KLAVE_BACKUP_BUCKET", "")
    instance = os.environ.get("EC2_INSTANCE_ID", "")
    if not re.fullmatch(r"i-[0-9a-f]{17}", instance) or not bucket:
        print("Backup monitor configuration missing.", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(run_once(Path("/backups"), bucket, Path("/state/s3-state.json"), instance))
