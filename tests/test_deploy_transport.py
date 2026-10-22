"""Transport preflight distinguishes failures without printing credentials."""

import importlib.util
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "deploy/transport_check.py"


@pytest.mark.parametrize(
    "error,category",
    [
        ("connect to host private-address port 22: Connection timed out", "network"),
        ("Host key verification failed", "host key"),
        ("Permission denied (publickey)", "authentication"),
        ("Could not resolve hostname private-address", "DNS"),
    ],
)
def test_preflight_failure_is_actionable_and_redacted(
    tmp_path, monkeypatch, capsys, error, category
):
    if not SCRIPT.exists():
        pytest.fail("transport preflight missing")
    spec = importlib.util.spec_from_file_location("transport_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def ssh(argv, **kwargs):
        assert "StrictHostKeyChecking=yes" in argv
        assert "BatchMode=yes" in argv
        assert kwargs["timeout"] <= 30
        return subprocess.CompletedProcess(argv, 255, "", error)

    monkeypatch.setattr(module.subprocess, "run", ssh)
    assert module.preflight("private-address", "ubuntu", tmp_path) != 0
    output = capsys.readouterr()
    assert category in output.err
    assert "private-address" not in output.err + output.out
