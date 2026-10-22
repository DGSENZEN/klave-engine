"""Restore only into newly allocated, owned scratch resources; never live klave."""

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from deploy import backup, smoke  # noqa: E402

OWNER = "klave-recovery-v1"


def validate_target(directory: Path) -> dict:
    marker = directory / "smoke.json"
    if directory.is_symlink() or marker.is_symlink() or not marker.is_file():
        raise ValueError("Recovery requires an owned smoke state directory")
    state = json.loads(marker.read_text())
    if (state.get("owner") != smoke.OWNER
            or not re.fullmatch(r"klave-smoke-[0-9a-f]{10}", state.get("project", ""))):
        raise ValueError("Recovery requires owned scratch resources")
    return state


def extract_safe(archive_path: Path, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise ValueError("Restore destination must be fresh")
    # Validate every member before creating even the destination directory.
    with tarfile.open(archive_path, "r:gz") as archive:
        members = backup.safe_members(archive)
        names = [member.name for member in members]
        if len(set(names)) != len(names):
            raise ValueError("Unsafe duplicate archive member")
        destination.mkdir(mode=0o700, parents=True)
        archive.extractall(destination, members=members, filter="data")


def dc(state: dict, *args: str) -> str:
    return smoke.command([
        "docker", "compose", "-p", state["project"], "-f",
        str(ROOT / "deploy/compose.recovery.yml"), *args,
    ], env={**os.environ, "KLAVE_API_IMAGE": state["api_image"],
            "KLAVE_RECOVERY_DATA": state["data"]}, timeout=240)


def cleanup(state: dict) -> None:
    if (state.get("owner") != OWNER
            or not re.fullmatch(r"klave-recovery-[0-9a-f]{20}", state.get("project", ""))):
        raise ValueError("Refusing cleanup of unowned recovery resources")
    # No caller-supplied project names, shared database URLs or volume IDs.
    dc(state, "down", "--volumes", "--remove-orphans")


def restore(directory: Path, source: Path) -> dict:
    original = validate_target(directory)
    manifest = backup.verify_backup(source)
    source_commit = manifest.get("source_commit", "unknown")
    image_commit = original.get("source_commit", "unknown")
    if source_commit != "unknown" and image_commit != "unknown" and source_commit != image_commit:
        raise ValueError("Restore requires a matching source commit and API image")
    # Verify before allocating directories, containers, databases or volumes.
    token = secrets.token_hex(10)
    target = directory / ("recovery-" + token)
    target.mkdir(mode=0o700)
    state = {"owner": OWNER, "project": "klave-recovery-" + token,
             "api_image": original.get("image_ids", {}).get("api_image", original["api_image"]),
             "data": str(target / "data"),
             "backup_stamp": manifest["stamp"]}
    state_file = target / "recovery.json"
    state_file.write_text(json.dumps(state))
    state_file.chmod(0o600)
    try:
        copied = target / "backup"
        copied.mkdir(mode=0o700)
        for name in (*backup.ARCHIVES, "manifest.json", "COMPLETE"):
            shutil.copyfile(source / name, copied / name)
        backup.verify_backup(copied)
        extract_safe(copied / "data.tar.gz", target / "data")
        extract_safe(copied / "sqlite.tar.gz", target / "sqlite")
        for path in (target / "sqlite").rglob("*"):
            if path.is_file():
                destination = target / "data" / path.relative_to(target / "sqlite")
                if destination.exists():
                    raise ValueError("Unsafe overlapping backup members")
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination)
        # A recorded state is not permission to attach to pre-existing resources.
        for kind, filter_name in (("ps", "label=com.docker.compose.project="),
                                  ("volume", "label=com.docker.compose.project=")):
            args = ["docker", kind]
            args += ["ls", "-q"] if kind == "volume" else ["-aq"]
            if smoke.command([*args, "--filter", filter_name + state["project"]]):
                raise ValueError("Scratch target must be fresh")
        state["allocated"] = True
        state_file.write_text(json.dumps(state))
        dc(state, "up", "-d", "--wait", "users-db")
        dc(state, "cp", str(copied / "users.dump"), "users-db:/tmp/users.dump")
        dc(state, "exec", "-T", "users-db", "pg_restore", "--exit-on-error", "--no-owner",
           "--no-acl", "-U", "klave_users", "-d", "klave_users", "/tmp/users.dump")
        dc(state, "up", "-d", "--wait", "api")
        state["api_url"] = "http://" + dc(state, "port", "api", "8000")
        wait_ready(state["api_url"])
        return state
    except BaseException:
        if state.get("allocated"):
            cleanup(state)
        raise


def wait_ready(url: str) -> None:
    import httpx

    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            if httpx.get(url + "/ready", timeout=3).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise RuntimeError("Scratch API did not become ready")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--backup", type=Path, required=True)
    args = parser.parse_args()
    state = None
    try:
        state = restore(args.state_dir.resolve(), args.backup.resolve())
        print("Scratch archive restoration and readiness passed; application acceptance pending.")
    except (ValueError, OSError, RuntimeError, KeyError, tarfile.TarError,
            subprocess.TimeoutExpired):
        print("Recovery failed; no recovery success is recorded.", file=sys.stderr)
        return 1
    finally:
        if state:
            cleanup(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
