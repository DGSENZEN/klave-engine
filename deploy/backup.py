"""Create and verify complete backups; credentials are never command arguments."""

import argparse
import gzip
import hashlib
import json
import os
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath

ARCHIVES = ("users.dump", "sqlite.tar.gz", "data.tar.gz")


def _run_pg(args: list[str]) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError("PostgreSQL backup tool failed")
    return result.stdout


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_members(archive: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members = archive.getmembers()
    for member in members:
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or not (member.isfile() or member.isdir()):
            raise ValueError("Unsafe backup archive member")
    return members


def verify_backup(directory: Path) -> dict:
    if directory.is_symlink() or not (directory / "COMPLETE").is_file():
        raise ValueError("Backup is not complete")
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest.get("format_version") != 1 or set(manifest.get("archives", {})) != set(ARCHIVES):
        raise ValueError("Invalid backup manifest")
    if (directory / "COMPLETE").read_text().strip() != manifest["stamp"]:
        raise ValueError("Invalid completion marker")
    for name in ARCHIVES:
        path = directory / name
        expected = manifest["archives"][name]
        if path.is_symlink() or path.stat().st_size != expected["size"]:
            raise ValueError("Backup archive integrity mismatch")
        if _digest(path) != expected["sha256"]:
            raise ValueError("Backup archive checksum mismatch")
        if name.endswith(".gz"):
            with gzip.open(path, "rb") as source:
                while source.read(1024 * 1024):
                    pass  # Read through the trailer, verifying the gzip CRC.
            with tarfile.open(path, "r:gz") as archive:
                safe_members(archive)
    _run_pg(["pg_restore", "--list", str(directory / "users.dump")])
    return manifest


def _snapshot_sqlite(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + 60

    def progress(status, remaining, total):
        if time.monotonic() > deadline:
            raise TimeoutError("SQLite backup timed out")

    with sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True) as original:
        with sqlite3.connect(destination) as copied:
            original.backup(copied, pages=256, progress=progress, sleep=0.1)
            if copied.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise ValueError("SQLite snapshot failed integrity check")


def _file_archive(destination: Path, files: list[Path], root: Path) -> None:
    with tarfile.open(destination, "w:gz") as archive:
        for path in files:
            if path.is_symlink():
                raise ValueError("Refusing a symlink in application data")
            with path.open("rb") as source:
                before = os.fstat(source.fileno())
                info = tarfile.TarInfo(path.relative_to(root).as_posix())
                info.size, info.mtime, info.mode = before.st_size, int(before.st_mtime), 0o600
                archive.addfile(info, source)
                after = os.fstat(source.fileno())
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise ValueError("Application file changed during backup")


def run_backup(data_dir: Path, backup_dir: Path, keep_days: int) -> Path:
    data_dir, backup_dir = data_dir.resolve(), backup_dir.resolve()
    if keep_days < 1 or backup_dir == data_dir or data_dir in backup_dir.parents:
        raise ValueError("Invalid retention or recursive backup destination")
    if not data_dir.is_dir():
        raise ValueError("Application data directory is missing")
    backup_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    stamp = now.strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(3)
    staging = backup_dir / (".partial-" + stamp)
    staging.mkdir(mode=0o700)
    final = backup_dir / stamp
    try:
        _run_pg([
            "pg_dump", "-h", os.environ.get("DB_HOST", "users-db"),
            "-p", os.environ.get("DB_PORT", "5432"),
            "-U", os.environ.get("DB_USER", "klave_users"),
            "-d", os.environ.get("DB_NAME", "klave_users"),
            "-Fc", "-f", str(staging / "users.dump"),
        ])
        files = sorted(path for path in data_dir.rglob("*") if path.is_file())
        snapshots = staging / "sqlite"
        snapshots.mkdir()
        for source in files:
            if source.suffix == ".db":
                if source.is_symlink():
                    raise ValueError("Refusing a symlink database")
                _snapshot_sqlite(source, snapshots / source.relative_to(data_dir))
        _file_archive(staging / "sqlite.tar.gz", sorted(snapshots.rglob("*.db")), snapshots)
        ordinary = [
            path for path in files
            if not path.name.endswith((".db", ".db-wal", ".db-shm", ".db-journal", ".part"))
            and ".health" not in path.relative_to(data_dir).parts
        ]
        _file_archive(staging / "data.tar.gz", ordinary, data_dir)
        shutil.rmtree(snapshots)
        manifest = {
            "format_version": 1, "stamp": stamp, "created_at": now.isoformat(),
            "archives": {
                name: {"size": (staging / name).stat().st_size,
                       "sha256": _digest(staging / name)} for name in ARCHIVES
            },
        }
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        (staging / "COMPLETE").write_text(stamp + "\n")
        verify_backup(staging)
        staging.rename(final)
    except BaseException:
        # Keep failed output for diagnosis; it must never look completed.
        (staging / "COMPLETE").unlink(missing_ok=True)
        raise
    cutoff = now - timedelta(days=keep_days)
    for directory in backup_dir.iterdir():
        if directory == final or not directory.is_dir() or directory.name.startswith("."):
            continue
        try:
            prior = verify_backup(directory)
            created = datetime.fromisoformat(prior["created_at"])
            if created < cutoff:
                shutil.rmtree(directory)
        except (ValueError, OSError, RuntimeError, KeyError, json.JSONDecodeError):
            continue  # Retention never removes an unverified directory.
    return final


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["once", "verify"])
    parser.add_argument("directory", nargs="?", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "verify":
            if args.directory is None:
                parser.error("verify requires a completed backup directory")
            verify_backup(args.directory)
            print("Backup integrity verified.")
        else:
            result = run_backup(
                Path(os.environ.get("DATA_DIR", "/data")),
                Path(os.environ.get("BACKUP_DIR", "/backups")),
                int(os.environ.get("BACKUP_KEEP_DAYS", "14")),
            )
            print("Complete backup: " + result.name)
    except (ValueError, OSError, RuntimeError, sqlite3.Error, subprocess.TimeoutExpired):
        print("Backup failed; no complete success is recorded.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
