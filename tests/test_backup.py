"""Backups preserve actual files/WAL data and never publish partial success."""

import importlib.util
import json
import sqlite3
import tarfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "deploy/backup.py"


def backup_module(monkeypatch):
    if not SCRIPT.exists():
        pytest.fail("verified backup implementation is missing")
    spec = importlib.util.spec_from_file_location("pilot_backup", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def pg(args, **kwargs):
        if args[0] == "pg_dump":
            Path(args[args.index("-f") + 1]).write_bytes(b"PGDMP synthetic external dump")
        return ""

    monkeypatch.setattr(module, "_run_pg", pg)
    return module


def test_snapshot_preserves_wal_and_unusual_names(tmp_path, monkeypatch):
    module = backup_module(monkeypatch)
    data = tmp_path / "data"
    data.mkdir()
    name = "un archivo 'ñ'\nplano.txt"
    (data / name).write_bytes(b"the drawing content")
    with sqlite3.connect(data / "catalog.db") as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE prices(value)")
        connection.execute("INSERT INTO prices VALUES (123)")
        connection.commit()
        directory = module.run_backup(data, tmp_path / "backups", 14)
    assert (directory / "COMPLETE").is_file()
    assert module.verify_backup(directory)["format_version"] == 1
    with tarfile.open(directory / "data.tar.gz") as archive:
        assert archive.extractfile(name).read() == b"the drawing content"
    with tarfile.open(directory / "sqlite.tar.gz") as archive:
        restored = tmp_path / "restored.db"
        restored.write_bytes(archive.extractfile("catalog.db").read())
    with sqlite3.connect(restored) as connection:
        assert connection.execute("SELECT value FROM prices").fetchall() == [(123,)]


def test_corrupted_archive_cannot_verify(tmp_path, monkeypatch):
    module = backup_module(monkeypatch)
    data = tmp_path / "data"
    data.mkdir()
    directory = module.run_backup(data, tmp_path / "backups", 14)
    (directory / "data.tar.gz").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="integrity|checksum|archive"):
        module.verify_backup(directory)


def test_dump_failure_never_prunes_last_complete_backup(tmp_path, monkeypatch):
    module = backup_module(monkeypatch)
    data = tmp_path / "data"
    data.mkdir()
    previous = module.run_backup(data, tmp_path / "backups", 1)

    def broken(*args, **kwargs):
        raise RuntimeError("dump unavailable")

    monkeypatch.setattr(module, "_run_pg", broken)
    with pytest.raises(RuntimeError):
        module.run_backup(data, tmp_path / "backups", 1)
    assert (previous / "COMPLETE").exists()
    complete = list((tmp_path / "backups").glob("*/COMPLETE"))
    assert complete == [previous / "COMPLETE"]


def test_invalid_retention_and_recursive_destination_are_rejected(tmp_path, monkeypatch):
    module = backup_module(monkeypatch)
    with pytest.raises(ValueError):
        module.run_backup(tmp_path, tmp_path / "inside", 14)
    with pytest.raises(ValueError):
        module.run_backup(tmp_path / "data", tmp_path / "backups", 0)


def test_manifest_cannot_reference_outside_files(tmp_path, monkeypatch):
    module = backup_module(monkeypatch)
    data = tmp_path / "data"
    data.mkdir()
    directory = module.run_backup(data, tmp_path / "backups", 14)
    manifest = json.loads((directory / "manifest.json").read_text())
    manifest["archives"]["../precious"] = {"size": 1, "sha256": "0" * 64}
    (directory / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        module.verify_backup(directory)


def test_manifest_records_source_commit_and_rejects_metadata_symlinks(tmp_path, monkeypatch):
    module = backup_module(monkeypatch)
    monkeypatch.setenv("KLAVE_SOURCE_COMMIT", "a" * 40)
    data = tmp_path / "data"
    data.mkdir()
    directory = module.run_backup(data, tmp_path / "backups", 14)
    assert module.verify_backup(directory)["source_commit"] == "a" * 40
    manifest = directory / "manifest.json"
    outside = tmp_path / "outside.json"
    manifest.rename(outside)
    manifest.symlink_to(outside)
    with pytest.raises(ValueError, match="metadata|symlink"):
        module.verify_backup(directory)


@pytest.mark.parametrize("broken", ["stamp", "archives", "metadata"])
def test_incomplete_manifest_is_rejected_as_invalid(tmp_path, monkeypatch, broken):
    module = backup_module(monkeypatch)
    data = tmp_path / "data"
    data.mkdir()
    directory = module.run_backup(data, tmp_path / "backups", 14)
    path = directory / "manifest.json"
    manifest = json.loads(path.read_text())
    if broken == "stamp":
        del manifest["stamp"]
    elif broken == "archives":
        manifest["archives"] = None
    else:
        manifest["archives"]["users.dump"] = {}
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="manifest"):
        module.verify_backup(directory)
