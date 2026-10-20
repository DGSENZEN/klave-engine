"""Owned, disposable real-service environment for the pilot browser suite."""

import argparse
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OWNER = "klave-pilot-test-v1"
LABEL = "mx.klave.pilot-test"


def claim_state_dir(directory: Path) -> None:
    directory = directory.resolve()
    marker = directory / ".klave-pilot-test"
    if marker.is_file():
        if marker.read_text() != OWNER:
            raise ValueError("Test directory is not owned by this harness")
        return
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("Test directory must be empty or owned by this harness")
    directory.mkdir(parents=True, exist_ok=True)
    marker.write_text(OWNER)
    directory.chmod(0o700)


def child_environment(directory: Path, database_url: str, inherited=None) -> dict[str, str]:
    inherited = os.environ if inherited is None else inherited
    env = {k: v for k, v in inherited.items()
           if not k.startswith(("KLAVE_", "NEXT_PUBLIC_"))
           and k not in {"ANTHROPIC_API_KEY", "GEMINI_API_KEY"}}
    env.update({
        "KLAVE_LOAD_DOTENV": "0",
        "KLAVE_ENV": "dev",
        "KLAVE_DATA_DIR": str(directory / "data"),
        "KLAVE_REPORTS_DIR": str(directory / "reports"),
        "KLAVE_USERS_DATABASE_URL": database_url,
        "KLAVE_WEB_ORIGIN": "http://127.0.0.1:13000",
        "KLAVE_REGISTRATION": "invite_only",
        "KLAVE_COOKIE_SECURE": "false",
        "KLAVE_MAIL_PROVIDER": "outbox",
        "KLAVE_LOG_LEVEL": "WARNING",
        "ANTHROPIC_API_KEY": "",
        "GEMINI_API_KEY": "",
        "NEXT_PUBLIC_API_URL": "http://127.0.0.1:18000",
        "NEXT_TELEMETRY_DISABLED": "1",
        "PYTHONPATH": str(ROOT),
    })
    return env


def check_ports(ports: list[int]) -> None:
    for port in ports:
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError as exc:
                raise RuntimeError(f"Test port {port} is occupied; refusing to reuse it") from exc


def docker(*args: str) -> str:
    result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise RuntimeError("Docker test service command failed")
    return result.stdout.strip()


def cleanup(directory: Path) -> None:
    marker = directory / ".klave-pilot-test"
    if not marker.is_file() or marker.read_text() != OWNER:
        raise ValueError("Refusing cleanup of an unowned test directory")
    resource = directory / "container.json"
    if resource.exists():
        name = json.loads(resource.read_text())["name"]
        owner = docker(
            "inspect", "--format", '{{index .Config.Labels "mx.klave.pilot-test"}}', name
        )
        if owner != directory.name:
            raise ValueError("Refusing cleanup of an unowned container")
        docker("rm", "-fv", name)
        resource.unlink()
    database = directory / "postgres.json"
    if database.exists():
        import psycopg
        from psycopg import sql

        state = json.loads(database.read_text())
        if not state["database"].startswith("klave_pilot_"):
            raise ValueError("Refusing cleanup of an unowned database")
        with psycopg.connect(state["admin_url"], autocommit=True, connect_timeout=2) as conn:
            conn.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(state["database"]))
            )
        database.unlink()


def seed(directory: Path, env: dict[str, str]) -> None:
    """Seed through normal stores; this is never exposed through the API."""
    os.environ.update(env)
    from klave_engine.common.config import get_settings
    from klave_engine.ingestion.project_loader import ingest_project

    from apps.api.auth.store import UserStore
    from apps.api.dependencies import ProjectStore

    get_settings.cache_clear()
    settings = get_settings()
    users = UserStore(settings.users_database_url)
    admin = users.create_user(
        email="admin@pilot.example", name="Pilot administrator", password="Synthetic-pilot-123!"
    )
    from apps.api.tenancy import workspace_store

    catalog = workspace_store(settings, str(admin["workspace_id"]))
    catalog.import_reference(
        {"key": "pilot-synthetic", "name": "Pilot synthetic prices", "kind": "precios_unitarios"},
        [{"clave": "PILOT-SLAB", "description": "Pilot slab area 4 x 3 m",
          "unit": "M2", "price": 1000}],
    )
    other = users.create_workspace("other-pilot", "Other pilot workspace")
    storage = ProjectStore(settings)
    project_ids = {}
    for key, workspace in (
        ("saved_unprocessed_project_id", admin["workspace_id"]),
        ("second_workspace_project_id", other["workspace_id"]),
    ):
        project_root = settings.data_dir / "uploads" / key
        (project_root / "drawings").mkdir(parents=True)
        shutil.copyfile(
            ROOT / "apps/web/e2e/fixtures/structural-meters.dxf",
            project_root / "drawings/structural.dxf",
        )
        manifest = ingest_project(project_root, processed_dir_name=settings.processed_dir_name)
        storage.register(manifest.project_id, project_root)
        users.register_project(manifest.project_id, str(workspace))
        if key == "saved_unprocessed_project_id":
            users.grant_access(manifest.project_id, str(admin["user_id"]), "owner", None)
        project_ids[key] = manifest.project_id
    state = {
        "web_url": "http://127.0.0.1:13000", "api_url": "http://127.0.0.1:18000",
        "admin_email": "admin@pilot.example", "admin_password": "Synthetic-pilot-123!",
        "invited_email": "customer@pilot.example",
        "expected_fixture_path": str(ROOT / "apps/web/e2e/fixtures/expected.json"),
        **project_ids,
    }
    path = directory / "state.json"
    path.write_text(json.dumps(state))
    path.chmod(0o600)


def wait_http(url: str, processes: list[subprocess.Popen], timeout: int = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if any(process.poll() is not None for process in processes):
            raise RuntimeError("Test service exited during startup")
        try:
            with urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (OSError, URLError):
            pass
        time.sleep(0.2)
    raise RuntimeError("Test service startup timed out")


def serve(directory: Path) -> None:
    claim_state_dir(directory)
    check_ports([13000, 18000])
    processes: list[subprocess.Popen] = []
    name = f"klave-pilot-{secrets.token_hex(5)}"
    try:
        import psycopg
        from psycopg import sql
        from psycopg.conninfo import conninfo_to_dict, make_conninfo

        admin_url = os.environ.get("PILOT_TEST_POSTGRES_URL")
        if admin_url:
            if conninfo_to_dict(admin_url).get("host") not in {"127.0.0.1", "localhost"}:
                raise ValueError("Native test database must be on loopback")
            database = f"klave_pilot_{secrets.token_hex(8)}"
            with psycopg.connect(admin_url, autocommit=True, connect_timeout=2) as conn:
                conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
            state = directory / "postgres.json"
            state.write_text(json.dumps({"admin_url": admin_url, "database": database}))
            state.chmod(0o600)
            database_url = make_conninfo(admin_url, dbname=database)
        else:
            docker("run", "-d", "--name", name, "--label", f"{LABEL}={directory.name}",
                   "-e", "POSTGRES_PASSWORD=synthetic-pilot-only",
                   "-e", "POSTGRES_DB=pilot", "-p", "127.0.0.1::5432", "postgres:16-alpine")
            (directory / "container.json").write_text(json.dumps({"name": name}))
            port = docker("port", name, "5432/tcp").rsplit(":", 1)[1]
            database_url = f"postgresql://postgres:synthetic-pilot-only@127.0.0.1:{port}/pilot"
        env = child_environment(directory, database_url)

        deadline = time.monotonic() + 60
        while True:
            try:
                with psycopg.connect(env["KLAVE_USERS_DATABASE_URL"], connect_timeout=2):
                    break
            except psycopg.OperationalError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Test database startup timed out") from None
                time.sleep(0.2)
        seed(directory, env)
        processes.append(subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "apps.api.main:app",
             "--host", "127.0.0.1", "--port", "18000", "--no-access-log"],
            cwd=ROOT, env=env, start_new_session=True,
        ))
        wait_http("http://127.0.0.1:18000/health", processes)
        processes.append(subprocess.Popen(
            ["npm", "run", "start", "--", "--hostname", "127.0.0.1", "--port", "13000"],
            cwd=ROOT / "apps/web", env=env, start_new_session=True,
        ))
        wait_http("http://127.0.0.1:13000/bienvenida", processes)
        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
        raise RuntimeError("Test service stopped unexpectedly")
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
        cleanup(directory)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["serve", "seed", "cleanup"])
    parser.add_argument("--state-dir", type=Path, required=True)
    args = parser.parse_args()
    directory = args.state_dir.resolve()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        if args.command == "serve":
            serve(directory)
        elif args.command == "cleanup":
            cleanup(directory)
        else:
            claim_state_dir(directory)
            seed(directory, child_environment(directory, os.environ["KLAVE_USERS_DATABASE_URL"]))
    except (ValueError, RuntimeError, subprocess.TimeoutExpired):
        print(
            "Pilot test setup failed; check owned resources and service availability.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
