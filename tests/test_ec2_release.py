"""Failed releases preserve the running API and never claim the new revision."""

import os
import subprocess
import tarfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "deploy/ec2-release.sh"
SHA = "a" * 40


def release(tmp_path, failure):
    root = tmp_path / "server"
    root.mkdir()
    (root / ".env.prod").write_text("KEEP=private\n")
    (root / "docker-compose.ec2.yml").write_text("previous compose\n")
    (root / ".release-current").write_text("previous\n")
    source = tmp_path / "source"
    source.mkdir()
    (source / "docker-compose.ec2.yml").write_text("candidate compose\n")
    archive = tmp_path / "release.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        output.add(source / "docker-compose.ec2.yml", arcname="docker-compose.ec2.yml")
    binaries = tmp_path / "bin"
    binaries.mkdir()
    (binaries / "sudo").write_text(
        '#!/bin/sh\ncase "$1" in --preserve-env=*) shift;; esac\nexec "$@"\n'
    )
    (binaries / "docker").write_text(
        '#!/bin/sh\n'
        'printf "%s %s\\n" "${KLAVE_API_IMAGE:-legacy}" "$*" >> "$CALLS"\n'
        'case "$1" in inspect) echo sha256:previous; exit 0;; esac\n'
        'case "$*" in\n'
        '  *"run --rm --no-deps backup once"*) '
        'if [ "$FAILURE" = stdin ]; then cat > /dev/null; fi; '
        '[ "$FAILURE" != backup ];;\n'
        '  *"up -d"*) [ "$FAILURE" != readiness ] || '
        '[ "${KLAVE_API_IMAGE:-}" = sha256:previous ];;\n'
        '  *) exit 0;;\n'
        'esac\n'
    )
    for path in binaries.iterdir():
        path.chmod(0o755)
    env = {**os.environ, "PATH": str(binaries) + ":" + os.environ["PATH"],
           "KLAVE_DEPLOY_DIR": str(root), "FAILURE": failure, "CALLS": str(tmp_path / "calls")}
    # macOS has no flock; the production host and CI runner are Linux.
    (binaries / "flock").write_text("#!/bin/sh\nexit 0\n")
    (binaries / "flock").chmod(0o755)
    command = ["bash", str(SCRIPT), SHA, str(archive)]
    stdin = None
    if failure == "stdin":
        command = ["bash", "-s", "--", SHA, str(archive)]
        stdin = SCRIPT.read_text()
    result = subprocess.run(command, input=stdin, env=env, capture_output=True, text=True)
    return root, (tmp_path / "calls"), result


@pytest.mark.parametrize("failure", ["backup", "readiness"])
def test_failed_release_recovers_previous_api_without_changing_revision(tmp_path, failure):
    root, calls, result = release(tmp_path, failure)
    assert result.returncode != 0
    assert (root / ".release-current").read_text() == "previous\n"
    assert (root / ".env.prod").read_text() == "KEEP=private\n"
    assert (root / "docker-compose.ec2.yml").read_text() == "previous compose\n"
    assert "sha256:previous" in calls.read_text()
    assert "down" not in calls.read_text()


def test_successful_release_records_only_ready_revision(tmp_path):
    root, _calls, result = release(tmp_path, "none")
    assert result.returncode == 0, result.stderr
    assert (root / ".release-current").read_text().strip() == SHA
    assert (root / ".env.prod").read_text() == "KEEP=private\n"


def test_release_over_ssh_stdin_finishes_after_attached_backup(tmp_path):
    root, calls, result = release(tmp_path, "stdin")
    assert result.returncode == 0, result.stderr
    assert (root / ".release-current").read_text().strip() == SHA
    assert "up -d" in calls.read_text()


def test_invalid_revision_does_not_touch_server(tmp_path):
    result = subprocess.run(["bash", str(SCRIPT), "../not-a-commit", str(tmp_path / "missing")],
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert list(tmp_path.iterdir()) == []
