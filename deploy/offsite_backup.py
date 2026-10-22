"""Copy and fetch back verified archives on operator-controlled mounted storage.

This does not establish off-host location, encryption, scheduling or alert delivery.
"""

import argparse
import json
import os
import secrets
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from deploy.backup import ARCHIVES, verify_backup  # noqa: E402


def copy_verified(source: Path, destination: Path, state_file: Path) -> None:
    manifest = verify_backup(source)
    source = source.resolve()
    if (
        destination.exists()
        or destination.is_symlink()
        or source == destination.resolve()
        or source in destination.resolve().parents
    ):
        raise ValueError("Copy destination must be fresh and separate from source")
    if source in state_file.resolve().parents:
        raise ValueError("Operator state must be separate from the backup")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / (".partial-copy-" + secrets.token_hex(10))
    staging.mkdir(mode=0o700)
    for name in (*ARCHIVES, "manifest.json", "COMPLETE"):
        shutil.copyfile(source / name, staging / name)
        (staging / name).chmod(0o600)
    verify_backup(staging)
    with tempfile.TemporaryDirectory(prefix="klave-backup-fetch-") as temporary:
        fetched = Path(temporary) / "backup"
        shutil.copytree(staging, fetched)
        verify_backup(fetched)
    staging.rename(destination)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "verified_at": datetime.now(UTC).isoformat(),
        "stamp": manifest["stamp"],
        "archives": manifest["archives"],
        "fetched_back": True,
        "off_host_and_encryption": "operator verification required",
    }
    temporary_state = state_file.parent / (".offsite-state-" + secrets.token_hex(10))
    with temporary_state.open("x", encoding="utf8") as output:
        os.chmod(temporary_state, 0o600)
        json.dump(state, output, indent=2)
    temporary_state.replace(state_file)


def is_current(state_file: Path, max_age_hours: float) -> bool:
    try:
        state = json.loads(state_file.read_text())
        when = datetime.fromisoformat(state["verified_at"])
        age = (datetime.now(UTC) - when).total_seconds()
        return max_age_hours > 0 and 0 <= age <= max_age_hours * 3600
    except (OSError, ValueError, KeyError, TypeError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["copy", "check-age"])
    parser.add_argument("--source", type=Path)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--max-age-hours", type=float, default=36)
    args = parser.parse_args()
    try:
        if args.action == "check-age":
            if not is_current(args.state, args.max_age_hours):
                print("Backup copy missing/stale; operator alert required.", file=sys.stderr)
                return 1
        else:
            if not args.source or not args.destination:
                parser.error("copy requires --source and --destination")
            copy_verified(args.source, args.destination, args.state)
            print("Complete backup copy and fetch-back integrity verified.")
    except (OSError, ValueError, RuntimeError, KeyError):
        print(
            "Backup copy failed; last success retained; operator alert required.", file=sys.stderr
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
