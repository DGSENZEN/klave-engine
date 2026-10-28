"""Synthetic application acceptance for the owned production-image restore drill."""

import hashlib
import importlib.util
import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx

from deploy import backup, smoke
from deploy import recovery_check as recovery

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "Synthetic-pilot-123!"
ADMIN = "admin@pilot.example"
OTHER = "other@pilot.example"

SEED = """
import json
from klave_engine.common.config import get_settings
from apps.api.auth.store import UserStore
from apps.api.tenancy import workspace_store
s = get_settings()
users = UserStore(s.users_database_url)
admin = users.get_by_email('admin@pilot.example')
other = users.create_workspace('recovery-other', 'Recovery other workspace')
users.create_user(email='other@pilot.example', name='Other workspace',
                  password='Synthetic-pilot-123!', workspace_id=str(other['workspace_id']))
catalog = workspace_store(s, str(admin['workspace_id']))
catalog.import_reference(
    {'key': 'pilot-synthetic', 'name': 'Pilot synthetic prices', 'kind': 'precios_unitarios'},
    [{'clave': 'PILOT-SLAB', 'description': 'Pilot slab area 4 x 3 m',
      'unit': 'M2', 'price': 1000}])
ref = next(r for r in catalog.list_reference_rows() if r['clave'] == 'PILOT-SLAB')
catalog.set_concept_alias('EST-016', kind='reference', ref_id=ref['ref_id'],
                          actor='Recovery operator')
workspace = users.get_workspace(str(admin['workspace_id']))
print(json.dumps({'workspace_slug': workspace['slug']}))
"""

FINGERPRINT = """
import hashlib, json
from klave_engine.common.config import get_settings
from apps.api.dependencies import ProjectStore
s = get_settings()
out = {}
for pid in PROJECTS:
    root = ProjectStore(s).get_root(pid)
    for path in (root / 'drawings').rglob('*'):
        if path.is_file():
            key = pid + '/' + path.relative_to(root).as_posix()
            out[key] = hashlib.sha256(path.read_bytes()).hexdigest()
print(json.dumps(out, sort_keys=True))
"""


@contextmanager
def login(url: str, email: str) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=url, timeout=60) as client:
        response = client.post("/auth/login", json={"email": email, "password": PASSWORD})
        response.raise_for_status()
        if response.json()["role"] != "admin":
            raise AssertionError("Restored account role changed")
        # Secure cookies are forwarded explicitly for this loopback-only drill.
        client.headers["Cookie"] = response.headers["set-cookie"].split(";", 1)[0]
        yield client


def upload(client: httpx.Client) -> str:
    drawing = ROOT / "apps/web/e2e/fixtures/structural-meters.dxf"
    response = client.post(
        "/projects/upload",
        files={
            "files": ("structural.dxf", drawing.read_bytes(), "application/octet-stream"),
        },
        data={"project_name": "Recovery synthetic project"},
    )
    response.raise_for_status()
    project_id = response.json()["project_id"]
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        status = client.get(f"/projects/{project_id}/status")
        status.raise_for_status()
        state = status.json()["state"]
        if state == "processed":
            return project_id
        if state in {"failed", "error"}:
            raise RuntimeError("Synthetic recovery project processing failed")
        time.sleep(0.5)
    raise RuntimeError("Synthetic processing timed out")


def workbook(client: httpx.Client, project_id: str, destination: Path) -> None:
    response = client.get(f"/projects/{project_id}/export/presupuesto.xlsx")
    response.raise_for_status()
    destination.write_bytes(response.content)
    spec = importlib.util.spec_from_file_location(
        "recovery_workbook", ROOT / "apps/web/e2e/check_workbook.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.check_workbook(destination, ROOT / "apps/web/e2e/fixtures/expected.json")


def fingerprint(compose, state, ids) -> dict:
    code = "PROJECTS = " + repr(ids) + "\n" + FINGERPRINT
    return json.loads(compose(state, "exec", "-T", "api", ".venv/bin/python", "-c", code))


def verify(url: str, expected: dict, output: Path) -> None:
    with login(url, ADMIN) as client:
        auth = client.get("/auth/session")
        auth.raise_for_status()
        assert auth.json()["workspace"]["slug"] == expected["workspace_slug"]
        project_id = expected["project_id"]
        assert client.get(f"/projects/{project_id}").status_code == 200
        reviews = client.get(f"/projects/{project_id}/reviews")
        reviews.raise_for_status()
        assert reviews.json()["verification"] == expected["verification"]
        aliases = client.get("/catalog/aliases")
        aliases.raise_for_status()
        assert aliases.json() == expected["aliases"]
        workbook(client, project_id, output)
        for suffix in ("", "/reviews", "/costs", "/export/presupuesto.xlsx"):
            assert client.get(f"/projects/{expected['other_project_id']}" + suffix).status_code in {
                403,
                404,
            }
    with login(url, OTHER) as client:
        assert client.get(f"/projects/{project_id}").status_code in {403, 404}


def run(directory: Path) -> None:
    state = recovery.validate_target(directory)
    url = "http://" + smoke.compose(state, "port", "api", "8000")
    seeded = json.loads(smoke.compose(state, "exec", "-T", "api", ".venv/bin/python", "-c", SEED))
    with login(url, ADMIN) as client:
        project_id = upload(client)
        for step in ("units", "detections", "assumptions"):
            response = client.put(
                f"/projects/{project_id}/reviews/verification",
                json={
                    "step": step,
                    "confirmed": True,
                },
            )
            response.raise_for_status()
        expected = {
            **seeded,
            "project_id": project_id,
            "verification": response.json()["verification"],
            "aliases": client.get("/catalog/aliases").json(),
        }
        workbook(client, project_id, directory / "original.xlsx")
    with login(url, OTHER) as client:
        expected["other_project_id"] = upload(client)
    ids = [project_id, expected["other_project_id"]]
    before = fingerprint(smoke.compose, state, ids)
    # Independently pinned drawing bytes, not just equality between two copies.
    source_hash = hashlib.sha256(
        (ROOT / "apps/web/e2e/fixtures/structural-meters.dxf").read_bytes()
    ).hexdigest()
    assert len(before) == 2 and set(before.values()) == {source_hash}
    smoke.compose(state, "stop", "api")
    try:
        # Linux bind mounts preserve container root ownership. Transfer only
        # this synthetic backup tree to the invoking runner, keeping mode 0700.
        smoke.compose(
            state,
            "run",
            "--rm",
            "--no-deps",
            "--entrypoint",
            "/bin/sh",
            "backup",
            "-c",
            'python3 /backup.py once && chown -R "$1:$2" /backups',
            "owned-synthetic-backup",
            str(os.getuid()),
            str(os.getgid()),
        )
        backups = directory / "backups"
        sources = [path for path in backups.iterdir() if (path / "COMPLETE").is_file()]
        assert len(sources) == 1
        manifest = backup.verify_backup(sources[0])
        for attempt in range(2):
            restored = recovery.restore(directory, sources[0])
            try:
                verify(restored["api_url"], expected, directory / f"restored-{attempt}.xlsx")
                assert fingerprint(recovery.dc, restored, ids) == before
            finally:
                recovery.cleanup(restored)

    finally:
        smoke.compose(state, "up", "-d", "--no-deps", "api")
        url = "http://" + smoke.compose(state, "port", "api", "8000")
        recovery.wait_ready(url)
    verify(url, expected, directory / "original-after.xlsx")
    assert fingerprint(smoke.compose, state, ids) == before
    (directory / "recovery-evidence.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "scope": "synthetic same-image restore only",
                "backup_stamp": manifest["stamp"],
                "source_commit": state["source_commit"],
                "lock_sha256": {
                    name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                    for name in ("uv.lock", "apps/web/package-lock.json")
                },
                "image_ids": state["image_ids"],
                "restores": 2,
                "source_sha256": source_hash,
                "checks": [
                    "login",
                    "workspace/role/access",
                    "catalog/alias",
                    "reviews",
                    "drawing hashes",
                    "canonical XLSX quantities/prices/evidence",
                    "isolation",
                ],
                "cross_version_rollback": "PENDING",
                "off_host": "PENDING",
            },
            indent=2,
        )
    )
    print((directory / "recovery-evidence.json").read_text())
    print("Two fresh synthetic restore/export drills passed; original data verified unchanged.")
