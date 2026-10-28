"""Copy complete backups to private versioned SSE-S3 storage and verify fetch-back."""

import argparse
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deploy.backup import ARCHIVES, verify_backup  # noqa: E402


def _aws(args: list[str]) -> dict:
    result = subprocess.run(
        [
            "aws",
            "--no-cli-pager",
            "--cli-connect-timeout",
            "10",
            "--cli-read-timeout",
            "60",
            "--output",
            "json",
            *args,
        ],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("AWS backup operation failed")
    value = json.loads(result.stdout or "{}")
    if not isinstance(value, dict):
        raise ValueError("Invalid AWS response")
    return value


def _encrypted_version(metadata: dict) -> str:
    version = metadata.get("VersionId")
    if (
        metadata.get("ServerSideEncryption") != "AES256"
        or not isinstance(version, str)
        or version in ("", "null")
    ):
        raise ValueError("S3 backup requires encryption and versioning")
    return version


def is_current(state_file: Path, max_age_hours: float) -> bool:
    try:
        state = json.loads(state_file.read_text())
        if (
            not isinstance(state, dict)
            or state.get("fetched_back") is not True
            or max_age_hours <= 0
        ):
            return False
        for key in ("verified_at", "backup_created_at"):
            age = (datetime.now(UTC) - datetime.fromisoformat(state[key])).total_seconds()
            if not 0 <= age <= max_age_hours * 3600:
                return False
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def copy_verified(source: Path, bucket: str, state_file: Path) -> None:
    if source.is_symlink():
        raise ValueError("Backup source must not be a symlink")
    source = source.resolve()
    if source == state_file.resolve() or source in state_file.resolve().parents:
        raise ValueError("Operator state must be separate from backup")
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket):
        raise ValueError("Invalid backup bucket")
    manifest = verify_backup(source)
    stamp = manifest["stamp"]
    if not re.fullmatch(r"\d{8}T\d{6}-[0-9a-f]{6}", stamp):
        raise ValueError("Invalid backup stamp")
    created_at = datetime.fromisoformat(manifest["created_at"])
    if created_at.tzinfo is None or created_at > datetime.now(UTC):
        raise ValueError("Invalid backup creation time")
    prefix = f"backups/{stamp}/{secrets.token_hex(8)}"
    versions = {}
    with tempfile.TemporaryDirectory(prefix="klave-s3-fetch-") as temporary:
        fetched = Path(temporary)
        required = sum(item["size"] for item in manifest["archives"].values())
        required += (source / "manifest.json").stat().st_size + (source / "COMPLETE").stat().st_size
        disk = os.statvfs(fetched)
        if (
            disk.f_bavail * disk.f_frsize < required + 2 * 1024**3
            or disk.f_files <= 0
            or disk.f_favail < 5 + disk.f_files * 0.05
        ):
            raise ValueError("Insufficient scratch capacity for verified fetch-back")
        for name in (*ARCHIVES, "manifest.json"):
            metadata = _aws(
                [
                    "s3api",
                    "put-object",
                    "--bucket",
                    bucket,
                    "--key",
                    f"{prefix}/{name}",
                    "--body",
                    str(source / name),
                    "--server-side-encryption",
                    "AES256",
                    "--if-none-match",
                    "*",
                ]
            )
            versions[name] = _encrypted_version(metadata)
            response = _aws(
                [
                    "s3api",
                    "get-object",
                    "--bucket",
                    bucket,
                    "--key",
                    f"{prefix}/{name}",
                    "--version-id",
                    versions[name],
                    str(fetched / name),
                ]
            )
            if _encrypted_version(response) != versions[name]:
                raise ValueError("S3 backup version mismatch")
            (fetched / name).chmod(0o600)
        (fetched / "COMPLETE").write_bytes((source / "COMPLETE").read_bytes())
        verify_backup(fetched)
        # Publish COMPLETE only after all archive bytes were downloaded and verified.
        metadata = _aws(
            [
                "s3api",
                "put-object",
                "--bucket",
                bucket,
                "--key",
                f"{prefix}/COMPLETE",
                "--body",
                str(source / "COMPLETE"),
                "--server-side-encryption",
                "AES256",
                "--if-none-match",
                "*",
            ]
        )
        versions["COMPLETE"] = _encrypted_version(metadata)
        response = _aws(
            [
                "s3api",
                "get-object",
                "--bucket",
                bucket,
                "--key",
                f"{prefix}/COMPLETE",
                "--version-id",
                versions["COMPLETE"],
                str(fetched / "COMPLETE"),
            ]
        )
        if (
            _encrypted_version(response) != versions["COMPLETE"]
            or (fetched / "COMPLETE").read_bytes() != (source / "COMPLETE").read_bytes()
        ):
            raise ValueError("S3 completion marker mismatch")
    state_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    state = {
        "verified_at": datetime.now(UTC).isoformat(),
        "backup_created_at": created_at.isoformat(),
        "stamp": stamp,
        "bucket": bucket,
        "prefix": prefix,
        "versions": versions,
        "archives": manifest["archives"],
        "source_commit": manifest.get("source_commit", "unknown"),
        "fetched_back": True,
        "encryption": "AES256",
    }
    temporary_state = state_file.parent / (".s3-state-" + secrets.token_hex(10))
    with temporary_state.open("x", encoding="utf8") as output:
        os.chmod(temporary_state, 0o600)
        json.dump(state, output, indent=2)
    temporary_state.replace(state_file)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    try:
        copy_verified(args.source, args.bucket, args.state)
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError):
        print("S3 copy/fetch-back verification failed; last success retained.", file=sys.stderr)
        return 1
    print("Versioned encrypted S3 copy and fetch-back integrity verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
