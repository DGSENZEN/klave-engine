"""Remote corruption or stale source data must never become a healthy backup."""

import importlib.util
import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "deploy/s3_backup.py"


def module():
    assert SCRIPT.is_file(), "S3 backup transport is not implemented"
    spec = importlib.util.spec_from_file_location("s3_backup", SCRIPT)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@pytest.fixture
def complete_backup(tmp_path, monkeypatch):
    from deploy import backup

    def pg(args):
        if args[0] == "pg_dump":
            Path(args[args.index("-f") + 1]).write_bytes(b"synthetic PostgreSQL dump")
        return ""

    monkeypatch.setattr(backup, "_run_pg", pg)
    data = tmp_path / "data"
    data.mkdir()
    (data / "drawing.dxf").write_bytes(b"preserved private drawing")
    return backup.run_backup(data, tmp_path / "backups", 7)


def s3_boundary(tmp_path, *, corrupt=False, encryption="AES256", version="version-1"):
    remote = tmp_path / "remote"
    remote.mkdir()

    def aws(args):
        operation = args[1]
        key = args[args.index("--key") + 1]
        path = remote / key
        if operation == "put-object":
            assert args[args.index("--if-none-match") + 1] == "*"
            assert not path.exists(), "A completed object was overwritten"
            assert args[args.index("--server-side-encryption") + 1] == "AES256"
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(args[args.index("--body") + 1], path)
        else:
            assert operation == "get-object"
            shutil.copyfile(path, args[-1])
            if corrupt and key.endswith("users.dump"):
                Path(args[-1]).write_bytes(b"remote corruption")
        return {"ServerSideEncryption": encryption, "VersionId": version}

    return aws


def test_copy_is_verified_from_s3_before_success_is_recorded(
    tmp_path, monkeypatch, complete_backup
):
    transport = module()
    monkeypatch.setattr(transport, "_aws", s3_boundary(tmp_path))
    state = tmp_path / "operator.json"
    transport.copy_verified(complete_backup, "private-backups", state)
    value = json.loads(state.read_text())
    assert value["fetched_back"] is True
    assert value["bucket"] == "private-backups"
    assert value["stamp"] == complete_backup.name
    assert value["versions"]["users.dump"] == "version-1"
    assert transport.is_current(state, 36)


@pytest.mark.parametrize("failure", ["corruption", "unencrypted", "unversioned"])
def test_remote_failure_retains_last_verified_state(
    tmp_path, monkeypatch, complete_backup, failure
):
    transport = module()
    monkeypatch.setattr(
        transport,
        "_aws",
        s3_boundary(
            tmp_path,
            corrupt=failure == "corruption",
            encryption="none" if failure == "unencrypted" else "AES256",
            version="null" if failure == "unversioned" else "version-1",
        ),
    )
    state = tmp_path / "operator.json"
    state.write_text("previous success")
    with pytest.raises((ValueError, RuntimeError)):
        transport.copy_verified(complete_backup, "private-backups", state)
    assert state.read_text() == "previous success"


def test_refetching_an_old_snapshot_cannot_reset_its_age(tmp_path):
    transport = module()
    state = tmp_path / "operator.json"
    state.write_text(
        json.dumps(
            {
                "verified_at": datetime.now(UTC).isoformat(),
                "backup_created_at": (datetime.now(UTC) - timedelta(hours=37)).isoformat(),
                "fetched_back": True,
            }
        )
    )
    assert not transport.is_current(state, 36)


def test_copy_rejects_state_inside_source_before_any_upload(tmp_path, monkeypatch, complete_backup):
    transport = module()
    monkeypatch.setattr(transport, "_aws", lambda args: pytest.fail("Upload before validation"))
    with pytest.raises(ValueError):
        transport.copy_verified(
            complete_backup, "private-backups", complete_backup / "manifest.json"
        )


def test_monitor_reports_failure_without_promoting_corrupted_remote_data(
    tmp_path,
    monkeypatch,
    complete_backup,
):
    spec = importlib.util.spec_from_file_location(
        "backup_monitor", SCRIPT.with_name("backup_monitor.py")
    )
    assert spec.origin and Path(spec.origin).exists(), "Independent backup heartbeat is missing"
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)
    remote = s3_boundary(tmp_path, corrupt=True)
    metrics = []

    def aws(args):
        if args[0] == "cloudwatch":
            metrics.extend(json.loads(args[args.index("--metric-data") + 1]))
            return {}
        return remote(args)

    monkeypatch.setattr(monitor.s3_backup, "_aws", aws)
    state = tmp_path / "state.json"
    assert (
        monitor.run_once(complete_backup.parent, "private-backups", state, "i-0123456789abcdef0")
        == 1
    )
    assert not state.exists()
    assert metrics[0]["Value"] == 0


def test_low_scratch_capacity_rejects_copy_before_upload(
    tmp_path,
    monkeypatch,
    complete_backup,
):
    from types import SimpleNamespace

    transport = module()
    monkeypatch.setattr(
        transport, "_aws", lambda args: pytest.fail("Upload despite low scratch space")
    )
    monkeypatch.setattr(
        transport.os,
        "statvfs",
        lambda path: SimpleNamespace(
            f_bavail=1024,
            f_frsize=4096,
            f_files=10000,
            f_favail=10000,
        ),
    )
    state = tmp_path / "operator.json"
    state.write_text("previous success")
    with pytest.raises(ValueError, match="scratch capacity"):
        transport.copy_verified(complete_backup, "private-backups", state)
    assert state.read_text() == "previous success"


def test_monitor_copies_intermediate_pre_upgrade_snapshots_too(
    tmp_path,
    monkeypatch,
    complete_backup,
):
    from deploy import backup_monitor as monitor

    original = complete_backup
    for name in ("20260101T000001-aaaaaa", "20260101T000002-bbbbbb"):
        target = original.parent / name
        shutil.copytree(original, target)
        manifest = json.loads((target / "manifest.json").read_text())
        manifest["stamp"] = name
        (target / "manifest.json").write_text(json.dumps(manifest))
        (target / "COMPLETE").write_text(name)
    shutil.rmtree(original)
    remote = s3_boundary(tmp_path)

    def aws(args):
        return {} if args[0] == "cloudwatch" else remote(args)

    monkeypatch.setattr(monitor.s3_backup, "_aws", aws)
    state = tmp_path / "state.json"
    assert monitor.run_once(original.parent, "private-backups", state, "i-0123456789abcdef0") == 0
    assert len(list((tmp_path / "remote").rglob("COMPLETE"))) == 2
    assert json.loads(state.read_text())["stamp"] == "20260101T000002-bbbbbb"
