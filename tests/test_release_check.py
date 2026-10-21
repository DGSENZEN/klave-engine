"""The shipping check rejects broken pilot configuration without leaking secrets."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "release_check.py"


def run_check(tmp_path, extra="", *, password="a" * 40):
    config = tmp_path / ".env.prod"
    config.write_text(
        f"KLAVE_DOMAIN=pilot.example.mx\nKLAVE_ACME_EMAIL=ops@example.mx\n"
        f"KLAVE_USERS_DB_PASSWORD={password}\nKLAVE_REGISTRATION=invite_only\n" + extra
    )
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--env-file", str(config)],
        text=True,
        capture_output=True,
        check=False,
    )


def test_valid_private_pilot_config(tmp_path):
    result = run_check(tmp_path)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "extra",
    [
        "KLAVE_DOMAIN=localhost\n",
        "KLAVE_DOMAIN=https://pilot.example.mx\n",
        "KLAVE_ACME_EMAIL=not-an-email\n",
        "KLAVE_REGISTRATION=open\n",
        "BACKUP_KEEP_DAYS=0\n",
        "KLAVE_COOKIE_SAMESITE=broken\n",
    ],
)
def test_rejects_unshippable_pilot_settings(tmp_path, extra):
    result = run_check(tmp_path, extra)
    assert result.returncode != 0


@pytest.mark.parametrize(
    "password", ["klave", "SUPERSECRET@password/with?characters123", "change-me"]
)
def test_rejects_weak_or_url_breaking_password_without_echoing_it(tmp_path, password):
    result = run_check(tmp_path, password=password)
    assert result.returncode != 0
    assert password not in result.stdout + result.stderr


def test_missing_config_has_actionable_error(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--env-file", str(tmp_path / "missing")],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Traceback" not in result.stderr


def runner():
    spec = importlib.util.spec_from_file_location("release_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_stage_failure_is_nonzero_and_redacts_secrets(tmp_path, capsys):
    module = runner()
    assert hasattr(module, "run_stage"), "named release stages are not implemented"
    result = module.run_stage(
        "browser", [sys.executable, "-c", "print('private-secret-value'); raise SystemExit(7)"],
        env={"KLAVE_USERS_DB_PASSWORD": "private-secret-value"}, cwd=tmp_path,
    )
    assert result == 7
    output = capsys.readouterr()
    assert "private-secret-value" not in output.out + output.err
    assert "browser" in output.out + output.err


def test_missing_required_tool_fails_the_stage(tmp_path):
    module = runner()
    assert hasattr(module, "run_stage"), "named release stages are not implemented"
    assert module.run_stage("container", [str(tmp_path / "missing")], env={}, cwd=tmp_path) != 0


def test_release_stages_include_browser_types_and_real_images():
    module = runner()
    assert hasattr(module, "stage_commands"), "full release stages are not implemented"
    names = [name for name, _ in module.stage_commands(Path("/tmp/owned-pilot"))]
    assert names.index("typecheck") < names.index("browser")
    assert {"python", "browser", "container-build", "container-check"} <= set(names)
