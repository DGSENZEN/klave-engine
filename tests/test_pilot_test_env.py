"""The browser harness must never inherit or overwrite a developer's state."""

import importlib.util
import socket
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/pilot_test_env.py"


def harness():
    if not SCRIPT.exists():
        pytest.fail("pilot harness is not implemented")
    spec = importlib.util.spec_from_file_location("pilot_test_env", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_rejects_nonempty_unowned_state_dir(tmp_path):
    original = tmp_path / "precious.txt"
    original.write_text("keep")
    with pytest.raises(ValueError, match="owned|empty"):
        harness().claim_state_dir(tmp_path)
    assert original.read_text() == "keep"


def test_claimed_directory_can_be_resumed_but_not_by_another_owner(tmp_path):
    module = harness()
    target = tmp_path / "test-run"
    module.claim_state_dir(target)
    assert (target / ".klave-pilot-test").is_file()
    module.claim_state_dir(target)
    (target / ".klave-pilot-test").write_text("different-owner")
    with pytest.raises(ValueError, match="owned"):
        module.claim_state_dir(target)


def test_ignores_inherited_production_settings(tmp_path):
    env = harness().child_environment(
        tmp_path,
        "postgresql://test:synthetic@127.0.0.1:6543/pilot",
        {"PATH": "/usr/bin", "KLAVE_ENV": "production",
         "KLAVE_DATA_DIR": "/precious", "ANTHROPIC_API_KEY": "secret",
         "KLAVE_USERS_DATABASE_URL": "postgresql://production"},
    )
    assert env["KLAVE_ENV"] == "dev"
    assert env["KLAVE_LOAD_DOTENV"] == "0"
    assert env["KLAVE_USERS_DATABASE_URL"].endswith(":6543/pilot")
    assert env["KLAVE_DATA_DIR"] == str(tmp_path / "data")
    assert env["ANTHROPIC_API_KEY"] == ""
    assert env["KLAVE_REGISTRATION"] == "invite_only"


def test_does_not_reuse_busy_ports():
    module = harness()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        with pytest.raises(RuntimeError, match="occupied"):
            module.check_ports([listener.getsockname()[1]])


def test_cleans_up_only_owned_resources_on_failure(tmp_path):
    module = harness()
    state = tmp_path / "run"
    module.claim_state_dir(state)
    sibling = tmp_path / "unrelated"
    sibling.mkdir()
    (sibling / "keep").write_text("yes")
    with pytest.raises(ValueError, match="owned"):
        module.cleanup(sibling)
    assert (sibling / "keep").read_text() == "yes"


def test_settings_opt_out_does_not_load_dotenv(tmp_path, monkeypatch):
    from klave_engine.common.config import get_settings

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("KLAVE_WORKSPACE_NAME=must-not-load\n")
    monkeypatch.setenv("KLAVE_LOAD_DOTENV", "0")
    monkeypatch.delenv("KLAVE_WORKSPACE_NAME", raising=False)
    get_settings.cache_clear()
    try:
        assert get_settings().workspace_name == "Taller"
    finally:
        get_settings.cache_clear()
