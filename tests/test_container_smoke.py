"""Smoke tooling refuses resources outside its own temporary project."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "deploy/smoke.py"


def smoke():
    if not SCRIPT.exists():
        pytest.fail("isolated container smoke is not implemented")
    spec = importlib.util.spec_from_file_location("container_smoke", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cleanup_rejects_unowned_directory(tmp_path):
    precious = tmp_path / "keep"
    precious.write_text("do not remove")
    with pytest.raises(ValueError, match="owned"):
        smoke().cleanup(tmp_path)
    assert precious.read_text() == "do not remove"


def test_smoke_state_cannot_be_rebound_to_another_project(tmp_path):
    module = smoke()
    state = module.claim(tmp_path / "run")
    assert state["project"].startswith("klave-smoke-")
    marker = tmp_path / "run" / "smoke.json"
    marker.write_text('{"project":"production","owner":"different"}')
    with pytest.raises(ValueError, match="owned"):
        module.claim(tmp_path / "run")
