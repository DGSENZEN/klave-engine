"""The bug this file exists to prevent: the presupuesto page correctly
refused to show a peso for a drawing with no reliable unit, while the project
list showed $768,759,055 for the same project as the most prominent thing on
the row. Two gating paths, one of them honest. Every money-bearing payload
must now carry the same verdict."""

import json

import pytest
from klave_engine.common import config as config_module
from klave_engine.costing.presentation import resolve_money_state

PROJECT_ID = "legacy_project_0001"

# A run from before money_basis existed: priced at factor 1.0 with no
# trustworthy unit, which is exactly the number nobody should see. This is
# Torre Reforma's shape, reduced to what the gate reads.
LEGACY_REPORT = {
    "project_id": PROJECT_ID,
    "currency": "MXN",
    "drawing_units": {
        "unit": "drawing_units", "source": "unknown", "confidence": 0.0, "notes": [],
    },
    "boq": {"project_id": PROJECT_ID, "lines": [], "direct_cost_total": 0.0},
    "apus": [],
    "integration": {"grand_total": 768759055.0},
    "schedule": {"activities": []},
    "financial": {},
}

# ProjectManifest.root_path is required with no default (see
# klave_engine.ingestion.manifest.ProjectManifest) — not part of the brief's
# original fixture, added here because model_validate rejects its absence.
MANIFEST = {
    "project_id": PROJECT_ID,
    "project_name": "Torre Reforma Nivel 1-2",
    "root_path": f"uploads/{PROJECT_ID}",
    "processing_status": "processed",
    "client": "Constructora GAYA",
    "archived": False,
    "source_files": [],
    "created_at": "2026-08-22T00:00:00+00:00",
}


@pytest.fixture
def legacy_client(data_dir, monkeypatch):
    """A TestClient over a data dir holding one legacy project.

    Built inline because the suite has no shared `client` fixture — see
    tests/test_projects_api.py, which does the same. `data_dir` comes from
    tests/conftest.py and resets the settings cache.

    Writing the artifacts under uploads/<id>/processed/ is not enough on its
    own: `/workspace/overview` and `/projects/{id}/costs` both resolve a
    project through ProjectStore.list_projects()/get_root(), which read the
    on-disk registry — not a directory scan. tests/test_retention.py:58-67
    establishes the pattern of registering a hand-staged project explicitly.
    """
    from fastapi.testclient import TestClient

    from apps.api.dependencies import ProjectStore
    from apps.api.main import create_app

    root = data_dir / "uploads" / PROJECT_ID
    processed = root / "processed"
    processed.mkdir(parents=True)
    (processed / "cost_report.json").write_text(
        json.dumps(LEGACY_REPORT), encoding="utf-8"
    )
    (processed / "project_manifest.json").write_text(
        json.dumps(MANIFEST), encoding="utf-8"
    )
    monkeypatch.setenv("KLAVE_USERS_DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    config_module.get_settings.cache_clear()
    client = TestClient(create_app())
    ProjectStore(config_module.get_settings()).register(PROJECT_ID, root)
    return client


def test_a_legacy_project_never_shows_a_total_on_the_list(legacy_client):
    rows = legacy_client.get("/workspace/overview").json()["projects"]
    row = next(r for r in rows if r["project_id"] == PROJECT_ID)

    assert row["money_state"] == "blocked"
    assert row["grand_total"] is None


def test_the_costs_endpoint_ships_the_resolved_verdict(legacy_client):
    payload = legacy_client.get(f"/projects/{PROJECT_ID}/costs").json()

    assert payload["money_state"] == "blocked"


def test_endpoint_returns_what_the_authority_says_rather_than_re_deriving(legacy_client):
    payload = legacy_client.get(f"/projects/{PROJECT_ID}/costs").json()

    assert payload["money_state"] == resolve_money_state(None, None)


def test_get_costs_degrades_to_blocked_instead_of_500_on_a_corrupt_basis(data_dir, monkeypatch):
    """workspace.py's report-reading block already tolerates a money_basis
    blob that fails to validate (KeyError/TypeError/ValueError/OSError, all
    swallowed to a blocked default). get_costs must be just as tolerant:
    a hand-edited or partially-migrated cost_report.json is exactly the kind
    of legacy data this feature exists to gate, not 500 on.

    Called directly rather than through a TestClient/app: get_costs never
    touches the manifest or the registry, so it needs neither — only a
    registered project root and its cost_report.json on disk.
    """
    from apps.api.dependencies import ProjectStore
    from apps.api.routes.reports import get_costs

    project_id = "corrupt_basis_0001"
    root = data_dir / "uploads" / project_id
    processed = root / "processed"
    processed.mkdir(parents=True)
    report = {
        "project_id": project_id,
        "currency": "MXN",
        "drawing_units": {
            "unit": "m", "source": "dxf_header", "confidence": 0.9, "notes": [],
        },
        "boq": {"project_id": project_id, "lines": [], "direct_cost_total": 0.0},
        "apus": [],
        "integration": {"grand_total": 0.0},
        "schedule": {"activities": []},
        "financial": {},
        # Malformed on purpose — confidence must be a number. This is what a
        # hand-edited or corrupted artifact looks like on disk.
        "money_basis": {"confidence": "not-a-number"},
    }
    (processed / "cost_report.json").write_text(json.dumps(report), encoding="utf-8")

    monkeypatch.setenv("KLAVE_USERS_DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    config_module.get_settings.cache_clear()
    settings = config_module.get_settings()
    store = ProjectStore(settings)
    store.register(project_id, root)

    payload = get_costs(project_id, store=store, settings=settings)

    assert payload["money_state"] == "blocked"


# ---------------------------------------------------------------- el bus ---
#
# The change timeline (ProjectLive.tsx) renders a costing_updated payload as
# "Total $X · ▲ $Y", on whatever project page is open — including the blocked
# project's own, three lines under its gate. Six places build that payload and
# only one of them resolved the verdict first, which is worse than none doing
# it: the inconsistency reads as deliberate.

def _blocked_report():
    """units_reliable=True and a real total — blocked only because the reading
    is 30 % confident and unconfirmed. A report whose total is already zero
    would satisfy any assertion below with no gate at all."""
    from klave_engine.costing.models import CostingConfig
    from klave_engine.costing.report import generate_cost_report
    from klave_engine.detection.results import DetectionType, make_detection
    from klave_engine.detection.taxonomy import classify_family
    from klave_engine.dxf.units import DrawingUnits

    from tests.precios import LIBRO

    wall = make_detection(
        "w1", DetectionType.wall, "w1", (0, 0, 10.0, 0.15), 0.9, [], "m", [],
        {"estimated_length": 10.0, "estimated_thickness": 0.15, "wall_kind": "block"},
    )
    wall.family = classify_family(wall).value
    return generate_cost_report(
        "p", [wall], DrawingUnits(unit="m", source="dxf_header", confidence=0.3),
        CostingConfig(), None, None, price_book=LIBRO,
    )


def test_no_blocked_total_is_publishable_but_a_confirmed_one_is():
    from datetime import UTC, datetime

    from klave_engine.costing.presentation import (
        publishable_stored_total,
        publishable_total,
    )
    from klave_engine.costing.reviews import VerificationState

    report = _blocked_report()
    assert report.integration.grand_total > 0  # there is a real total to leak

    assert publishable_total(report, None) is None
    assert publishable_total(report, VerificationState()) is None
    # Confirming the unit is what unblocks it — the same join every surface makes.
    confirmed = VerificationState(units_confirmed_at=datetime.now(UTC))
    assert publishable_total(report, confirmed) == report.integration.grand_total

    stored = report.model_dump(mode="json")
    assert publishable_stored_total(stored, None) is None
    assert publishable_stored_total(stored, confirmed) == report.integration.grand_total
    # The "before" half of a delta comes off disk, where it can be anything.
    assert publishable_stored_total(LEGACY_REPORT, confirmed) is None  # no basis at all
    assert publishable_stored_total({"integration": {}}, confirmed) is None
    assert publishable_stored_total(None, confirmed) is None


def test_no_broadcast_reads_a_grand_total_straight_off_a_report():
    """Structural, and deliberately so: the defect was not one wrong number,
    it was five publishers of one payload drifting apart while a sixth was
    added. Any future ``BUS.publish`` whose data dict takes a total directly
    off a report — instead of through the authority — fails here, in the file
    that states the contract, rather than silently on someone's screen.

    ``pipeline.py``'s ``_run_diff`` is held to the same rule: its two totals
    become run_diff.json, which the project page renders as a peso delta."""
    import ast
    import pathlib

    def offenders(tree: ast.AST) -> list[str]:
        found = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_publish = (
                isinstance(func, ast.Attribute)
                and func.attr == "publish"
                and isinstance(func.value, ast.Name)
                and func.value.id == "BUS"
            )
            is_diff = isinstance(func, ast.Name) and func.id == "_run_diff"
            if not (is_publish or is_diff):
                continue
            values: list[ast.expr] = list(node.args)
            for keyword in node.keywords:
                if keyword.arg == "data" and isinstance(keyword.value, ast.Dict):
                    values.extend(
                        value
                        for key, value in zip(
                            keyword.value.keys, keyword.value.values, strict=True
                        )
                        if isinstance(key, ast.Constant)
                        and str(key.value).endswith("grand_total")
                    )
            for value in values:
                for inner in ast.walk(value):
                    if isinstance(inner, ast.Attribute) and inner.attr == "grand_total":
                        found.append(f"línea {inner.lineno}: {ast.unparse(value)}")
        return found

    root = pathlib.Path(__file__).resolve().parents[1]
    files = sorted((root / "apps" / "api" / "routes").glob("*.py"))
    files.append(root / "packages" / "klave_engine" / "pipeline.py")
    scanned = 0
    problems: dict[str, list[str]] = {}
    for path in files:
        source = path.read_text(encoding="utf-8")
        if "grand_total" not in source:
            continue
        scanned += 1
        bad = offenders(ast.parse(source))
        if bad:
            problems[path.name] = bad

    assert scanned >= 5, f"sólo se revisaron {scanned} archivos: la prueba no probó nada"
    assert not problems, problems
