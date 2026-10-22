"""A failed copy cannot replace the last verified destination or success state."""

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "deploy/offsite_backup.py"


def offsite():
    if not SCRIPT.exists():
        pytest.fail("verified offsite copy missing")
    spec = importlib.util.spec_from_file_location("offsite", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_copy_rejects_incomplete_backup_without_mutating_destination(tmp_path):
    module = offsite()
    source = tmp_path / "incomplete"
    source.mkdir()
    with pytest.raises(ValueError, match="complete"):
        module.copy_verified(source, tmp_path / "destination", tmp_path / "state.json")
    assert not (tmp_path / "destination").exists()
    assert not (tmp_path / "state.json").exists()


def test_missing_stale_and_future_success_records_fail_age_check(tmp_path):
    module = offsite()
    path = tmp_path / "state.json"
    assert not module.is_current(path, 36)
    for hours in (-1, 37):
        path.write_text(
            json.dumps({"verified_at": (datetime.now(UTC) - timedelta(hours=hours)).isoformat()})
        )
        assert not module.is_current(path, 36)
    path.write_text(json.dumps({"verified_at": datetime.now(UTC).isoformat()}))
    assert module.is_current(path, 36)


def test_complete_copy_is_fetched_and_failure_retains_last_success(tmp_path, monkeypatch):
    from deploy import backup

    module = offsite()

    def pg(args):
        if args[0] == "pg_dump":
            Path(args[args.index("-f") + 1]).write_bytes(b"synthetic PostgreSQL dump")
        return ""

    monkeypatch.setattr(backup, "_run_pg", pg)
    data = tmp_path / "data"
    data.mkdir()
    (data / "drawing.dxf").write_bytes(b"preserved drawing")
    source = backup.run_backup(data, tmp_path / "backups", 14)
    target = tmp_path / "controlled-storage" / "first"
    state = tmp_path / "operator.json"
    module.copy_verified(source, target, state)
    assert backup.verify_backup(target)["stamp"] == source.name

    previous = state.read_bytes()
    assert json.loads(previous)["fetched_back"] is True

    original_copy = module.shutil.copyfile

    def corrupt(source, destination, *args, **kwargs):
        result = original_copy(source, destination, *args, **kwargs)
        if Path(destination).name == "users.dump":
            Path(destination).write_bytes(b"corruption")
        return result

    monkeypatch.setattr(module.shutil, "copyfile", corrupt)
    failed = target.parent / "second"
    with pytest.raises(ValueError, match="integrity|checksum"):
        module.copy_verified(source, failed, state)
    assert not failed.exists()
    assert state.read_bytes() == previous
    assert backup.verify_backup(target)["stamp"] == source.name


@pytest.mark.parametrize("state_name", ["manifest.json", "users.dump", "COMPLETE", "nested/state"])
def test_operator_state_cannot_overwrite_the_completed_copy(tmp_path, monkeypatch, state_name):
    from deploy import backup

    module = offsite()

    def pg(args):
        if args[0] == "pg_dump":
            Path(args[args.index("-f") + 1]).write_bytes(b"synthetic PostgreSQL dump")
        return ""

    monkeypatch.setattr(backup, "_run_pg", pg)
    data = tmp_path / "data"
    data.mkdir()
    source = backup.run_backup(data, tmp_path / "backups", 14)
    target = tmp_path / "destination"
    with pytest.raises(ValueError, match="state|separate"):
        module.copy_verified(source, target, target / state_name)
    assert not target.exists()
