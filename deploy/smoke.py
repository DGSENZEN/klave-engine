"""Build and check production images only in a uniquely owned Compose project."""

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OWNER = "klave-container-smoke-v1"


def claim(directory: Path) -> dict:
    marker = directory / "smoke.json"
    if marker.exists():
        state = json.loads(marker.read_text())
        if state.get("owner") != OWNER or not state.get("project", "").startswith("klave-smoke-"):
            raise ValueError("Container resources are not owned by this smoke run")
        return state
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)
    sha = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True
    ).strip()
    project = "klave-smoke-" + secrets.token_hex(5)
    state = {
        "owner": OWNER, "project": project,
        "api_image": f"klave-api:{sha}-{project}", "web_image": f"klave-web:{sha}-{project}",
    }
    marker.write_text(json.dumps(state))
    marker.chmod(0o600)
    return state


def command(argv: list[str], *, env: dict | None = None, timeout: int = 120) -> str:
    result = subprocess.run(
        argv, cwd=ROOT, env=env, text=True, capture_output=True, timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError("Owned container command failed: " + argv[0])
    return result.stdout.strip()


def compose(state: dict, *args: str, timeout: int = 120) -> str:
    env = {**os.environ, "KLAVE_API_IMAGE": state["api_image"],
           "KLAVE_WEB_IMAGE": state["web_image"]}
    return command([
        "docker", "compose", "-p", state["project"], "-f", str(ROOT / "deploy/compose.smoke.yml"),
        *args,
    ], env=env, timeout=timeout)


def cleanup(directory: Path) -> None:
    if not (directory / "smoke.json").is_file():
        raise ValueError("Refusing cleanup of an unowned smoke directory")
    state = claim(directory)
    compose(state, "down", "--volumes", "--remove-orphans")


def build(directory: Path) -> None:
    state = claim(directory)
    command([
        "docker", "build", "-f", "apps/api/Dockerfile", "-t", state["api_image"], ".",
    ], timeout=1800)
    command([
        "docker", "build", "-f", "apps/web/Dockerfile", "--build-arg",
        "NEXT_PUBLIC_API_URL=https://api.pilot.example.mx", "-t", state["web_image"], "apps/web",
    ], timeout=1200)
    state["image_ids"] = {
        key: command(["docker", "image", "inspect", "--format", "{{.Id}}", state[key]])
        for key in ("api_image", "web_image")
    }
    (directory / "smoke.json").write_text(json.dumps(state))


def check(directory: Path) -> None:
    import httpx

    state = claim(directory)
    try:
        compose(state, "up", "-d", "--wait", timeout=180)
        api = "http://" + compose(state, "port", "api", "8000")
        web = "http://" + compose(state, "port", "web", "3000")
        with httpx.Client(base_url=api, timeout=10) as client:
            assert client.get("/health").status_code == 200
            assert client.get("/catalog").status_code == 403
            compose(state, "exec", "-T", "api", ".venv/bin/python", "-m",
                    "apps.api.auth.cli", "create-workspace", "pilot", "Pilot")
            invitation = compose(
                state, "exec", "-T", "api", ".venv/bin/python", "-m",
                "apps.api.auth.cli", "invite-admin", "pilot", "admin@pilot.example",
            )
            from urllib.parse import parse_qs, urlparse

            url = next(line.strip() for line in invitation.splitlines() if "token=" in line)
            token = parse_qs(urlparse(url).query)["token"][0]
            accepted = client.post("/auth/invitations/by-token/" + token + "/accept", json={
                "name": "Pilot administrator", "password": "Synthetic-pilot-123!",
            })
            if accepted.status_code != 201:
                raise RuntimeError("Container bootstrap invitation could not be accepted")
            cookie = accepted.headers["set-cookie"].split(";", 1)[0]
            assert client.get("/workspace/overview", headers={"Cookie": cookie}).status_code == 200
            assert httpx.get(web, timeout=10).status_code == 200
            compose(state, "exec", "-T", "api", ".venv/bin/python", "-c",
                    "from pathlib import Path; Path('/data/.smoke-marker').write_text('persisted')")
            compose(state, "restart", "api")
            # Docker can allocate a new ephemeral host port on restart.
            restarted_api = "http://" + compose(state, "port", "api", "8000")
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                try:
                    if httpx.get(restarted_api + "/health", timeout=2).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.5)
            else:
                raise RuntimeError("Restarted API did not become live")
            assert httpx.get(
                restarted_api + "/workspace/overview", headers={"Cookie": cookie}, timeout=10,
            ).status_code == 200
            marker = compose(
                state, "exec", "-T", "api", ".venv/bin/python", "-c",
                "from pathlib import Path; print(Path('/data/.smoke-marker').read_text())",
            )
            assert marker == "persisted"
            compose(state, "exec", "-T", "api", "dwg2dxf", "--version")
        print("Owned production-image smoke passed.")
    finally:
        cleanup(directory)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["build", "check", "cleanup"])
    parser.add_argument("--state-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        {"build": build, "check": check, "cleanup": cleanup}[args.action](args.state_dir.resolve())
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired, AssertionError):
        print("Container verification failed; no release success is recorded.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
