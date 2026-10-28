"""An SSM configuration error must never fall back to public SSH."""

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "deploy/ssm_proxy.py"


@pytest.mark.parametrize(
    "instance,region", [("", "us-east-2"), ("i-abc;id", "us-east-2"), ("i-0123456789abcdef0", "")]
)
def test_invalid_ssm_configuration_fails_before_starting_session(instance, region, monkeypatch):
    monkeypatch.setenv("EC2_INSTANCE_ID", instance)
    monkeypatch.setenv("AWS_REGION", region)
    result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode != 0
    assert "Invalid SSM transport configuration" in result.stderr
    if instance:
        assert instance not in result.stderr


def test_proxy_uses_only_the_fixed_ssh_document(tmp_path, monkeypatch):
    import os

    executable = tmp_path / "aws"
    executable.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    executable.chmod(0o700)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("EC2_INSTANCE_ID", "i-0123456789abcdef0")
    monkeypatch.setenv("AWS_REGION", "us-east-2")
    result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "ssm",
        "start-session",
        "--target",
        "i-0123456789abcdef0",
        "--region",
        "us-east-2",
        "--document-name",
        "Klave-DeploymentSSH",
    ]
