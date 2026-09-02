# Confianza del número — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

> **Cerrado 2026-09-02:** las trece tareas aterrizaron en la rama
> `worktree-confianza-del-numero` (28 commits) y se consolidaron a `main` en
> el merge `ddd4f75` junto con la integración como análisis. La definición
> de hecho está fenceada: `test_money_state_contract`, `test_presentation`,
> `test_schedule_precedence`, `test_conteos`, `test_hallazgos_grouping` en
> verde; gold money intacto; ruff, tsc, eval-gold y eval-demo verdes sobre
> el árbol fundido. Nota del merge: la migración de reorden pasó a **v24**
> (v22 ya era EST-016) y el registro del programa se espeja desde
> `schedule.assumptions`, nunca se redacta dos veces.

**Goal:** Make Klave's output stop contradicting its own honesty doctrine — one authority decides whether a number may be shown as money, the programa stops scheduling formwork after its own pour, findings stop drowning their signal — and open the measurement loop every accuracy claim depends on.

**Architecture:** The presentation verdict moves out of three divergent per-surface implementations into one pure function in `costing/presentation.py`, resolved server-side and rendered by the client. The schedule's derived concepts (acero, cimbra) gain a `sequence_order` against the pour they serve, and the pours gain FS edges. Findings group by rule id. Human counts land in the project store beside reviews.

**Tech Stack:** Python 3.11+ / pydantic v2 / FastAPI / pytest · Next.js 15 + TypeScript + Tailwind · SQLite catalog store with a numbered migration chain

**Spec:** `docs/superpowers/specs/2026-08-25-confianza-del-numero-design.md`

## Global Constraints

- **Not one peso moves in this round.** Every change is presentation, grouping, or dates. `tests/test_gold_money.py` and `make eval-gold` must pass unchanged at every commit. Any moved amount is a bug in this round.
- **Spanish stays in the product.** All user-facing strings, finding text, warnings and column headers are Mexican Spanish. Code identifiers, docstrings and comments follow the file they live in (this codebase writes English docstrings with Spanish domain nouns).
- **No invented numbers.** A value the engine cannot derive is rendered as an honest absence (`sin precio`, `sin unidades`, `no se sabe`) — never `0`, never a guess. This applies to new code exactly as it does to existing code.
- **Confidence threshold is 0.70**, defined today as `CONFIDENCE_FIRM` in `apps/web/components/ui.tsx:477` and as the `>= 0.7` floor in `DrawingUnits.reliable` (`packages/klave_engine/dxf/units.py:51`). Do not change the value in this round; only how it is presented.
- **Run from the repo root** with the project venv: `.venv/bin/python -m pytest …`, `.venv/bin/ruff check .`, `.venv/bin/mypy packages/klave_engine`. Web checks: `apps/web/node_modules/.bin/tsc -p apps/web/tsconfig.json --noEmit`.
- **Every task ends green**: `ruff`, `mypy` and the full `pytest` suite pass before the commit.

---

## File Structure

**Created**

| Path | Responsibility |
|---|---|
| `packages/klave_engine/costing/presentation.py` | `MoneyBasis`, `MoneyState`, `resolve_money_state`, `money_basis_from_boq`. Pure; no I/O, no imports from `apps/`. |
| `packages/klave_engine/costing/conteos.py` | `ConteoHoja`, `ConteosDeProyecto`, load/save against the project control dir. |
| `tests/test_presentation.py` | Table tests for the resolver, including legacy missing-basis. |
| `tests/test_money_state_contract.py` | Every money-bearing endpoint ships `money_state`. |
| `tests/test_schedule_precedence.py` | The pour invariant, link dedupe, FS placement. |
| `tests/test_hallazgos_grouping.py` | Same-rule findings collapse, ordering by amount. |
| `tests/test_conteos.py` | Conteos round-trip; recall reads the project store. |

**Modified**

| Path | Change |
|---|---|
| `packages/klave_engine/costing/models.py` | `money_basis` field on `CostReport`; `sequence_order` docstring note |
| `packages/klave_engine/costing/report.py` | Build and attach `MoneyBasis` |
| `packages/klave_engine/costing/schedule.py` | Dedupe links, FS forward-pass branch, frentes assumption text |
| `packages/klave_engine/costing/catalog_store.py` | `DERIVADO_DE` map + migration v22 (data only — the catalog is already spaced by 10, so `catalog.py`, `steel.py` and `formwork.py` are untouched) |
| `packages/klave_engine/costing/hallazgos.py` | `HallazgoGrupo`; group by rule id |
| `packages/klave_engine/costing/exports.py` | Four `units_reliable` checks → resolver |
| `packages/klave_engine/evals/recall_cli.py` | Read project store first |
| `apps/api/routes/workspace.py` | Gate `grand_total`; emit `money_state` |
| `apps/api/routes/reports.py` | Enrich `/costs` with `money_state` |
| `apps/api/routes/copilot.py` | Gate its `grand_total` reads |
| `apps/api/routes/reviews.py` | Conteos endpoints |
| `apps/web/components/MoneyGate.tsx` | `moneyGate()` deleted; renders `money_state` |
| `apps/web/lib/api.ts` | `money_state`, `money_basis`, conteos types |
| `apps/web/app/page.tsx` | Rows lead with unresolved |
| `apps/web/app/proyecto/[id]/presupuesto/page.tsx` | Bands; grouped findings |
| `apps/web/app/proyecto/[id]/programa/page.tsx` | Frentes control |
| `apps/web/app/proyecto/[id]/revision/page.tsx` | Conteos input |
| `docs/evals.md`, `docs/recall.md`, `docs/principios-de-interfaz.md` | The ritual; counts move; one authority |

---

## Task 1: The resolver

**Files:**
- Create: `packages/klave_engine/costing/presentation.py`
- Test: `tests/test_presentation.py`

**Interfaces:**
- Consumes: `BillOfQuantities` and `DrawingUnits` (existing), `VerificationState` from `klave_engine.costing.reviews`
- Produces, **in `models.py`** (pre-flight ruling R1 — see Task 2 Step 3 for why): `MoneyBasis`, a pydantic model with fields `units_reliable: bool`, `unit: str`, `source: str`, `confidence: float`, `reasons: list[str]`, `confidence_bands: dict[str, float]`
- Produces, **in `presentation.py`**: `MoneyState = Literal["ok","unverified","blocked"]`; `CONFIDENCE_FIRM = 0.7`; `resolve_money_state(basis: MoneyBasis | None, verification: VerificationState | None) -> MoneyState`; `money_basis_from_boq(boq: BillOfQuantities, units: DrawingUnits) -> MoneyBasis`; `basis_reasons(basis: MoneyBasis | None) -> list[str]`

> **Pre-flight ruling R1:** define `MoneyBasis` in `models.py` beside the other
> domain models, and import it into `presentation.py`. Do **not** define it in
> `presentation.py` — that module imports `BillOfQuantities` from `models.py`,
> so defining `MoneyBasis` there and importing it back would be a cycle. The
> code block in Step 3 below shows `MoneyBasis` inside `presentation.py`;
> ignore that placement and put the class in `models.py`, keeping every
> function in `presentation.py` exactly as written.

- [x] **Step 1: Write the failing test**

Create `tests/test_presentation.py`:

```python
"""One authority decides whether a number may be shown as money. This is
that authority's truth table — including the legacy runs written before the
verdict existed, which must not be readable as money."""

from datetime import UTC, datetime

import pytest
from klave_engine.costing.models import BillOfQuantities, BoqLine, QuantityKind
from klave_engine.costing.presentation import (
    MoneyBasis,
    money_basis_from_boq,
    resolve_money_state,
)
from klave_engine.costing.reviews import VerificationState
from klave_engine.dxf.units import DrawingUnits

CONFIRMED = VerificationState(units_confirmed_at=datetime.now(UTC), units_confirmed_by="ing")
UNCONFIRMED = VerificationState()


def basis(*, reliable=True, unit="m", source="dxf_header", confidence=0.9) -> MoneyBasis:
    return MoneyBasis(
        units_reliable=reliable, unit=unit, source=source, confidence=confidence,
        reasons=[], confidence_bands={},
    )


@pytest.mark.parametrize(
    "given, verification, expected",
    [
        # The engine priced nothing: no sign-off can turn that into money.
        (basis(reliable=False, unit="drawing_units", source="unknown", confidence=0.0),
         CONFIRMED, "blocked"),
        (basis(reliable=False), UNCONFIRMED, "blocked"),
        # Read with confidence but nobody signed: money with the banner.
        (basis(), UNCONFIRMED, "unverified"),
        (basis(), CONFIRMED, "ok"),
        # A lone weak heuristic is a suggestion, not a scale.
        (basis(source="text_height_heuristic", confidence=0.4), UNCONFIRMED, "blocked"),
        # ...until a person confirms it, which is exactly what sign-off is for.
        (basis(source="text_height_heuristic", confidence=0.4), CONFIRMED, "ok"),
        # A run written before money_basis existed carries no verdict at all.
        (None, UNCONFIRMED, "blocked"),
        (None, CONFIRMED, "blocked"),
    ],
)
def test_every_combination_of_engine_reading_and_human_signoff(given, verification, expected):
    assert resolve_money_state(given, verification) == expected


def test_legacy_run_says_why_it_is_blocked():
    state = resolve_money_state(None, UNCONFIRMED)
    assert state == "blocked"


def test_bands_weigh_money_not_lines():
    """One expensive doubtful line must not be hidden by many cheap sure ones."""
    boq = BillOfQuantities(project_id="p")
    boq.lines = [
        BoqLine(concept_code="A", description="cara y dudosa", unit="M3", quantity=1,
                unit_price=900.0, amount=900.0, phase="Estructura", raw_quantity=1,
                raw_kind=QuantityKind.COUNT, source_detection_count=1, confidence=0.70),
        BoqLine(concept_code="B", description="barata y segura", unit="PZA", quantity=1,
                unit_price=100.0, amount=100.0, phase="Estructura", raw_quantity=1,
                raw_kind=QuantityKind.COUNT, source_detection_count=1, confidence=0.95),
    ]
    boq.direct_cost_total = 1000.0
    units = DrawingUnits(unit="m", source="dxf_header", confidence=0.9)

    bands = money_basis_from_boq(boq, units).confidence_bands

    assert bands["en_el_limite"] == pytest.approx(90.0)
    assert bands["alta"] == pytest.approx(10.0)
    assert sum(bands.values()) == pytest.approx(100.0)
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_presentation.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'klave_engine.costing.presentation'`

- [x] **Step 3: Write the implementation**

Create `packages/klave_engine/costing/presentation.py`:

```python
"""Whether a number may be shown as money — decided once, here.

Before this module the rule lived in three places at three levels of rigor:
the web joined report and reviews correctly, the exports checked only
``units_reliable``, and the project list checked nothing at all. A doctrine
rule re-derived per surface is a doctrine that decays with every surface
added, and the newest one always gets the weakest version.

The split is forced by ``set_verification``, which deliberately does not
recompute: a full verdict frozen into ``cost_report.json`` would still read
"unverified" long after a person confirmed the unit. So the artifact carries
only what the engine read; the human half stays in reviews; this module joins
them at read time.
"""

from typing import Literal

from pydantic import BaseModel, Field

from klave_engine.costing.models import BillOfQuantities
from klave_engine.costing.reviews import VerificationState
from klave_engine.dxf.units import DrawingUnits

MoneyState = Literal["ok", "unverified", "blocked"]

# The floor a reading has to clear to be treated as firm, mirrored in the web
# as CONFIDENCE_FIRM. One number, two languages, stated in both.
CONFIDENCE_FIRM = 0.7

LEGACY_REASON = "corrida anterior sin veredicto de unidades"


class MoneyBasis(BaseModel):
    """What the engine read about the drawing's scale, frozen with the run.

    Stable for the life of a run: re-reading the plan is what changes it, and
    that always produces a new run.
    """

    units_reliable: bool = True
    unit: str = ""
    source: str = ""
    confidence: float = 0.0
    # Why, in the words the screens already use.
    reasons: list[str] = Field(default_factory=list)
    # Share of the direct cost by confidence band, in percent. Money-weighted
    # on purpose: a simple average lets a hundred safe screws hide one
    # doubtful beam.
    confidence_bands: dict[str, float] = Field(default_factory=dict)


def money_basis_from_boq(boq: BillOfQuantities, units: DrawingUnits) -> MoneyBasis:
    reasons: list[str] = []
    if not boq.units_reliable:
        reasons.append(
            "La unidad del plano no es confiable: las cantidades están en unidades "
            "de dibujo y ninguna línea lleva precio."
        )
    elif units.confidence < CONFIDENCE_FIRM:
        reasons.append(
            f"Unidad leída como {units.unit} con {units.confidence:.0%} de confianza "
            f"(fuente: {units.source})."
        )
    return MoneyBasis(
        units_reliable=boq.units_reliable,
        unit=units.unit,
        source=units.source,
        confidence=units.confidence,
        reasons=reasons,
        confidence_bands=_confidence_bands(boq),
    )


def _confidence_bands(boq: BillOfQuantities) -> dict[str, float]:
    """Direct cost split three ways by the confidence behind it.

    Three bands rather than a pass rate because a single threshold lets a
    quarter of the money sit exactly on the line and still report "100 %
    firme" — which is the screen looking better than the reading behind it.
    """
    total = sum(line.amount for line in boq.lines)
    if total <= 0:
        return {}
    bands = {"alta": 0.0, "media": 0.0, "en_el_limite": 0.0}
    for line in boq.lines:
        if line.confidence > CONFIDENCE_FIRM:
            bands["alta"] += line.amount
        elif line.confidence == CONFIDENCE_FIRM:
            bands["en_el_limite"] += line.amount
        else:
            bands["media"] += line.amount
    return {key: round(value / total * 100.0, 1) for key, value in bands.items()}


def resolve_money_state(
    basis: MoneyBasis | None, verification: VerificationState | None
) -> MoneyState:
    """The one rule every money surface obeys.

    ``None`` basis means a run written before this verdict existed. It is
    blocked, not trusted: those runs priced at factor 1.0 when the unit was
    unknown, which is exactly the number nobody should see.
    """
    if basis is None:
        return "blocked"
    # The engine's own verdict wins: without a reliable unit it priced nothing,
    # so there is no amount for a person to sign off on.
    if not basis.units_reliable:
        return "blocked"
    if verification is not None and verification.units_confirmed_at is not None:
        return "ok"
    trustworthy = basis.unit != "drawing_units" and basis.confidence >= CONFIDENCE_FIRM
    return "unverified" if trustworthy else "blocked"


def basis_reasons(basis: MoneyBasis | None) -> list[str]:
    """What to tell the reader when money is withheld."""
    return [LEGACY_REASON] if basis is None else list(basis.reasons)
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_presentation.py -q`
Expected: PASS — 11 passed

- [x] **Step 5: Verify nothing else moved**

Run: `.venv/bin/python -m pytest tests -q -p no:warnings && .venv/bin/ruff check . && .venv/bin/mypy packages/klave_engine`
Expected: 540+ passed (baseline in this worktree is 540), `All checks passed!`, `Success: no issues found`

- [x] **Step 6: Commit**

```bash
git add packages/klave_engine/costing/presentation.py tests/test_presentation.py
git commit -m "feat(presentacion): una sola autoridad decide si un numero puede verse como dinero"
```

---

## Task 2: Attach the basis to the report

**Files:**
- Modify: `packages/klave_engine/costing/models.py` (`CostReport`, after `indirectos_campo`)
- Modify: `packages/klave_engine/costing/report.py:~360` (the `CostReport(...)` construction)
- Test: `tests/test_presentation.py` (append)

**Interfaces:**
- Consumes: `money_basis_from_boq` from Task 1
- Produces: `CostReport.money_basis: MoneyBasis | None` — every consumer in Tasks 3–5 reads this field

- [x] **Step 1: Write the failing test**

Append to `tests/test_presentation.py`:

```python
def test_the_report_carries_its_own_basis():
    """The verdict travels with the run, so a surface never has to re-derive it."""
    from klave_engine.costing.models import CostingConfig
    from klave_engine.costing.report import generate_cost_report
    from klave_engine.detection.results import DetectionType, make_detection
    from klave_engine.detection.taxonomy import classify_family

    from tests.precios import LIBRO

    wall = make_detection(
        "w1", DetectionType.wall, "w1", (0, 0, 10.0, 0.15), 0.9, [], "m", [],
        {"estimated_length": 10.0, "estimated_thickness": 0.15, "wall_kind": "block"},
    )
    wall.family = classify_family(wall).value
    units = DrawingUnits(unit="m", source="dxf_header", confidence=0.9)

    report = generate_cost_report(
        "p", [wall], units, CostingConfig(), None, None, price_book=LIBRO
    )

    assert report.money_basis is not None
    assert report.money_basis.units_reliable is True
    assert report.money_basis.unit == "m"
    assert sum(report.money_basis.confidence_bands.values()) == pytest.approx(100.0, abs=0.2)


def test_an_unreadable_drawing_produces_a_basis_that_blocks():
    from klave_engine.costing.models import CostingConfig
    from klave_engine.costing.report import generate_cost_report
    from klave_engine.detection.results import DetectionType, make_detection
    from klave_engine.detection.taxonomy import classify_family

    from tests.precios import LIBRO

    wall = make_detection(
        "w1", DetectionType.wall, "w1", (0, 0, 10.0, 0.15), 0.9, [], "u", [],
        {"estimated_length": 10.0, "estimated_thickness": 0.15, "wall_kind": "block"},
    )
    wall.family = classify_family(wall).value
    unknown = DrawingUnits(unit="drawing_units", source="unknown", confidence=0.0)

    report = generate_cost_report(
        "p", [wall], unknown, CostingConfig(), None, None, price_book=LIBRO
    )

    assert resolve_money_state(report.money_basis, UNCONFIRMED) == "blocked"
    assert resolve_money_state(report.money_basis, CONFIRMED) == "blocked"
    assert report.money_basis.reasons  # it says why, not just no
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_presentation.py -q -k "carries_its_own_basis or unreadable_drawing"`
Expected: FAIL — `AttributeError: 'CostReport' object has no attribute 'money_basis'`

- [x] **Step 3: Add the field**

> **Pre-flight ruling R1 — `MoneyBasis` lives in `models.py`, not `presentation.py`.**
> The original plan put the model in `presentation.py`, which imports
> `BillOfQuantities` from `models.py` — so `models.py` importing it back
> created a cycle survivable only via a bottom-of-file import plus
> `model_rebuild()`. `MoneyBasis` is a pydantic domain model like every other
> one in this file, so it belongs here, and the dependency runs one way:
> `presentation` → `models`, never back. Task 1 defines `MoneyBasis` in
> `models.py` and imports it into `presentation.py`; no `model_rebuild()`
> anywhere.

In `packages/klave_engine/costing/models.py`, inside `class CostReport`, after `indirectos_campo: float = 0.0`:

```python
    # What the engine read about the drawing's scale, frozen with this run.
    # Joined with the reviews' sign-off by costing.presentation at read time;
    # None on runs written before the verdict existed, which resolve to
    # "blocked" rather than being trusted.
    money_basis: MoneyBasis | None = None
```

`MoneyBasis` is defined earlier in this same file (Task 1), so this is a plain
forward-free annotation — no quotes, no rebuild.

- [x] **Step 4: Populate it**

In `packages/klave_engine/costing/report.py`, add to the imports:

```python
from klave_engine.costing.presentation import money_basis_from_boq
```

Then in the `CostReport(...)` construction (the call that already passes `indirectos_campo=indirectos_campo`), add:

```python
        money_basis=money_basis_from_boq(boq, units),
```

- [x] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_presentation.py -q`
Expected: PASS — 13 passed

- [x] **Step 6: Verify no peso moved**

Run: `.venv/bin/python -m pytest tests/test_gold_money.py -q && .venv/bin/python -m pytest tests -q -p no:warnings && .venv/bin/mypy packages/klave_engine`
Expected: all pass. If `test_gold_money` fails, stop — this task must not change an amount.

- [x] **Step 7: Commit**

```bash
git add packages/klave_engine/costing/models.py packages/klave_engine/costing/report.py tests/test_presentation.py
git commit -m "feat(presentacion): el reporte carga su propio veredicto de unidades"
```

---

## Task 3: Every server surface asks the authority

**Files:**
- Modify: `apps/api/routes/workspace.py:73-150` (`_project_overview` — note: NOT `_project_entry`)
- Modify: `apps/api/routes/reports.py:35-38` (`get_costs`)
- Modify: `apps/api/routes/copilot.py:200-232`
- Modify: `packages/klave_engine/costing/exports.py:164, 263, 340, 377`
- Test: `tests/test_money_state_contract.py`

**Interfaces:**
- Consumes: `resolve_money_state`, `basis_reasons`, `MoneyBasis` (Task 1); `CostReport.money_basis` (Task 2)
- Produces: every money-bearing JSON payload carries `money_state: MoneyState`; blocked rows carry `grand_total: None`

- [x] **Step 1: Write the failing test**

Create `tests/test_money_state_contract.py`:

```python
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

MANIFEST = {
    "project_id": PROJECT_ID,
    "project_name": "Torre Reforma Nivel 1-2",
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
    """
    from fastapi.testclient import TestClient

    from apps.api.main import create_app

    processed = data_dir / "uploads" / PROJECT_ID / "processed"
    processed.mkdir(parents=True)
    (processed / "cost_report.json").write_text(
        json.dumps(LEGACY_REPORT), encoding="utf-8"
    )
    (processed / "project_manifest.json").write_text(
        json.dumps(MANIFEST), encoding="utf-8"
    )
    monkeypatch.setenv("KLAVE_USERS_DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    config_module.get_settings.cache_clear()
    return TestClient(create_app())


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
```

If `project_manifest.json` needs more fields than `MANIFEST` carries, read
`klave_engine.ingestion`'s manifest model and add exactly the required ones —
do not loosen the manifest model to make the test pass. If the overview
response shape is not `{"projects": [...]}`, read `apps/api/routes/workspace.py`'s
`overview()` return value and match it.

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_money_state_contract.py -q`
Expected: FAIL — `KeyError: 'money_state'`, and `grand_total` is `768759055.0` rather than `None`

- [x] **Step 3: Gate the project list**

In `apps/api/routes/workspace.py`, add to the imports:

```python
from klave_engine.costing.presentation import MoneyBasis, resolve_money_state
```

Add `"money_state": "blocked"` to the default `entry` dict beside `"grand_total": None`.

Then replace the report-reading block (currently `entry["grand_total"] = report["integration"]["grand_total"]`) with:

```python
        try:
            report = read_json(report_path)
            raw_basis = report.get("money_basis")
            basis = MoneyBasis.model_validate(raw_basis) if raw_basis else None
            state = resolve_money_state(basis, verification)
            entry["money_state"] = state
            # A total the presupuesto refuses to show is a total the list may
            # not show either: one authority, every surface.
            entry["grand_total"] = (
                None if state == "blocked" else report["integration"]["grand_total"]
            )
            entry["currency"] = report.get("currency", "MXN")
        except (KeyError, TypeError, ValueError, OSError):
            pass
```

`verification` is already in scope — it is read from `load_reviews(control_dir)` earlier in the same function.

- [x] **Step 4: Enrich the costs endpoint**

In `apps/api/routes/reports.py`, replace `get_costs`:

```python
@router.get("/{project_id}/costs")
def get_costs(
    project_id: str,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """The report as stored, plus the verdict resolved against today's
    sign-off. The verdict is not stored because confirming a unit changes no
    number and therefore triggers no recompute: a frozen verdict would read
    "unverified" forever."""
    report = store.read_artifact(project_id, "cost_report.json")
    control_dir = store.get_root(project_id) / settings.processed_dir_name
    raw_basis = report.get("money_basis")
    basis = MoneyBasis.model_validate(raw_basis) if raw_basis else None
    report["money_state"] = resolve_money_state(basis, load_reviews(control_dir).verification)
    return report
```

Add to that file's imports:

```python
from klave_engine.costing.presentation import MoneyBasis, resolve_money_state
```

- [x] **Step 5: Gate the copilot and the exports**

In `apps/api/routes/copilot.py`, both places that read `report.integration.grand_total` (around lines 202 and 223) must not hand a blocked total to the model. Wrap each read:

```python
    state = resolve_money_state(report.money_basis, reviews.verification)
    total = None if state == "blocked" else report.integration.grand_total
```

and pass `total` where `grand_total` was passed. Add the import as in Step 4. `reviews` is already loaded in both call sites; if a call site lacks it, load it with `load_reviews(control_dir)` following the pattern in `reports.py`.

In `packages/klave_engine/costing/exports.py`, the four sites currently reading `report.boq.units_reliable` (lines 164, 263, 340, 377) become:

```python
    if resolve_money_state(report.money_basis, verification) == "blocked":
```

`build_presupuesto_workbook` must accept a `verification: VerificationState | None = None` parameter and thread it to the four sites. Update `apps/api/routes/exports.py` to pass `load_reviews(control_dir).verification`.

- [x] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_money_state_contract.py -q`
Expected: PASS — 3 passed

- [x] **Step 7: Verify the whole suite and no moved peso**

Run: `.venv/bin/python -m pytest tests -q -p no:warnings && .venv/bin/ruff check . && .venv/bin/mypy packages/klave_engine`
Expected: all green

- [x] **Step 8: Commit**

```bash
git add apps/api/routes/workspace.py apps/api/routes/reports.py apps/api/routes/copilot.py apps/api/routes/exports.py packages/klave_engine/costing/exports.py tests/test_money_state_contract.py
git commit -m "fix(dinero): la lista deja de mostrar el total que el presupuesto niega"
```

---

## Task 4: The client stops deriving the verdict

**Files:**
- Modify: `apps/web/components/MoneyGate.tsx:23-34` (delete `moneyGate`, keep the renderers)
- Modify: `apps/web/lib/api.ts` (types)
- Modify: `apps/web/app/proyecto/[id]/page.tsx:233,239`, `presupuesto/page.tsx:162`, `apus/page.tsx:101`, `programa/page.tsx:95`, `flujo/page.tsx:64`
- Modify: `apps/web/app/page.tsx:730-735`

**Interfaces:**
- Consumes: `money_state` on the `/costs` payload and on overview rows (Task 3)
- Produces: `moneyState(costs)` — a one-line accessor replacing the two-document join

- [x] **Step 1: Add the types**

In `apps/web/lib/api.ts`, add near the `CostReport` type. **Reuse the existing
`MoneyGateState` union** exported from `components/MoneyGate.tsx` rather than
declaring a second name for the same three values — two names for one union
drift the moment someone adds a fourth state:

```typescript
import type { MoneyGateState } from "@/components/MoneyGate";

export type MoneyBasis = {
  units_reliable: boolean;
  unit: string;
  source: string;
  confidence: number;
  reasons: string[];
  /** Share of direct cost by confidence band, in percent. */
  confidence_bands: Record<string, number>;
};
```

Add to the `CostReport` type: `money_state?: MoneyGateState;` and `money_basis?: MoneyBasis | null;`

Add to the overview project row type: `money_state?: MoneyGateState;`

If importing from a component into `lib/` inverts the dependency direction this
codebase uses, move `MoneyGateState` into `lib/api.ts` and re-export it from
`MoneyGate.tsx` so the six existing importers keep working unchanged.

- [x] **Step 2: Replace the gate with an accessor**

In `apps/web/components/MoneyGate.tsx`, delete the `moneyGate` function entirely and replace it with:

```typescript
/**
 * The verdict is resolved on the server by costing.presentation, because the
 * rule used to live here, in the exports, and in the project list at three
 * different levels of rigor — and the newest surface always got the weakest
 * one. The client renders the answer; it no longer derives it.
 */
export function moneyState(costs: CostReport | null): MoneyGateState {
  return costs?.money_state ?? "ok";
}
```

Keep `MoneyGateState`, `UnverifiedBanner` and `UnitsGate` as they are, changing their internal `moneyGate(costs, reviews)` calls to `moneyState(costs)`.

- [x] **Step 3: Update the six call sites**

In each of `app/proyecto/[id]/page.tsx`, `presupuesto/page.tsx`, `apus/page.tsx`, `programa/page.tsx`, `flujo/page.tsx`, change the import from `moneyGate` to `moneyState` and every call `moneyGate(costs, reviews)` to `moneyState(costs)`. Do not change the surrounding conditionals.

- [x] **Step 4: Rows lead with what is unresolved**

In `apps/web/app/page.tsx`, replace the total block (currently `{project.grand_total != null && (…)}`) with:

```tsx
      {project.money_state === "blocked" ? (
        <div className="text-right">
          <div className="text-sm text-muted">sin unidades</div>
          <div className="microlabel">confirma la escala</div>
        </div>
      ) : (
        project.grand_total != null && (
          <div className="text-right">
            <div className="tabular-nums">
              {money(project.grand_total, project.currency)}
            </div>
            <div className="microlabel">total</div>
          </div>
        )
      )}
```

- [x] **Step 5: Verify types and the running app**

Run: `apps/web/node_modules/.bin/tsc -p apps/web/tsconfig.json --noEmit`
Expected: exit 0, no output

Then start the dev servers and confirm in the browser that the Torre Reforma row reads **sin unidades** instead of `$768,759,055`, and that Marina still shows its total with the SIN VERIFICAR banner.

- [x] **Step 6: Commit**

```bash
git add apps/web
git commit -m "fix(web): el cliente lee el veredicto, ya no lo deduce"
```

---

## Task 5: Confidence becomes a distribution

**Files:**
- Modify: `apps/web/app/proyecto/[id]/presupuesto/page.tsx` (the "IMPORTE EN LECTURAS FIRMES" tile)
- Test: manual, plus the band assertions already in `tests/test_presentation.py`

**Interfaces:**
- Consumes: `costs.money_basis.confidence_bands` (Tasks 1–2)

- [x] **Step 1: Replace the pass rate with the bands**

Find the tile rendering `IMPORTE EN LECTURAS FIRMES` and `100%`. Replace its value and help text with:

```tsx
{(() => {
  const bands = costs?.money_basis?.confidence_bands;
  if (!bands || Object.keys(bands).length === 0) return <span>—</span>;
  return (
    <div className="flex flex-col gap-1">
      <div className="tabular-nums">
        {bands.alta?.toFixed(0) ?? 0}% alta
        {bands.en_el_limite ? ` · ${bands.en_el_limite.toFixed(0)}% en el límite` : ""}
        {bands.media ? ` · ${bands.media.toFixed(0)}% media` : ""}
      </div>
    </div>
  );
})()}
```

Change the help text to:

> Del costo directo, cuánto descansa en lecturas de confianza alta, cuánto queda justo en el umbral de 70 % y cuánto por debajo. Pesa el dinero, no cuenta elementos: un promedio simple deja que cien tornillos seguros tapen una trabe dudosa. Una sola tasa de aprobación escondería que un cuarto del importe está exactamente en la raya.

- [x] **Step 2: Verify in the running app**

Run the dev servers, open Marina Lote 04 — Completo → Presupuesto.
Expected: roughly `76% alta · 24% en el límite`, not `100%`.

- [x] **Step 3: Verify types**

Run: `apps/web/node_modules/.bin/tsc -p apps/web/tsconfig.json --noEmit`
Expected: exit 0

- [x] **Step 4: Commit**

```bash
git add apps/web/app/proyecto/\[id\]/presupuesto/page.tsx
git commit -m "fix(presupuesto): la confianza se reparte en bandas, no en una tasa de aprobacion"
```

---

## Task 6: Deduplicate the schedule links

**Files:**
- Modify: `packages/klave_engine/costing/schedule.py:171-200`
- Test: `tests/test_schedule_precedence.py`

**Interfaces:**
- Produces: `ScheduleActivity.predecessors` holds at most one link per `(predecessor, kind)`

- [x] **Step 1: Write the failing test**

Create `tests/test_schedule_precedence.py`:

```python
"""The programa is handed to a client citing RLOPSRM art. 224. These are the
things that must be true of it before that is defensible."""

from klave_engine.costing.models import CostingConfig
from klave_engine.costing.report import generate_cost_report
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.taxonomy import classify_family
from klave_engine.dxf.units import DrawingUnits

from tests.precios import LIBRO


def _structural_report():
    """A column and a beam: enough to produce concrete, its steel and its
    formwork, which is where every ordering bug in this file lives."""
    detections = []
    for index in range(6):
        column = make_detection(
            f"c{index}", DetectionType.column_tag, f"C-{index}",
            (index, 0, index + 0.3, 0.3), 0.9, [], "m", [],
            {"section_cm": "30x30"},
        )
        column.family = classify_family(column).value
        detections.append(column)
    for index in range(4):
        beam = make_detection(
            f"b{index}", DetectionType.beam_tag, f"T-{index}",
            (0, index, 5.0, index + 0.3), 0.9, [], "m", [],
            {"estimated_span_length": 5.0, "section_cm": "30x60"},
        )
        beam.family = classify_family(beam).value
        detections.append(beam)
    units = DrawingUnits(unit="m", source="dxf_header", confidence=0.9)
    return generate_cost_report(
        "p", detections, units, CostingConfig(), None, None, price_book=LIBRO
    )


def test_no_activity_lists_the_same_predecessor_twice():
    """The step anchor and the crew tail are often the same concept, and both
    branches used to append their own link — 13 of 30 activities on Marina."""
    report = _structural_report()

    for activity in report.schedule.activities:
        seen = [(link.predecessor, link.kind) for link in activity.predecessors]
        assert len(seen) == len(set(seen)), f"{activity.concept_code} repite {seen}"


def test_deduplication_keeps_the_binding_lag():
    """Two links to one predecessor mean two constraints; the later start wins."""
    report = _structural_report()

    for activity in report.schedule.activities:
        for link in activity.predecessors:
            predecessor = next(
                (a for a in report.schedule.activities if a.concept_code == link.predecessor),
                None,
            )
            if predecessor is None:
                continue
            if link.kind == "SS":
                assert activity.start_day >= predecessor.start_day + link.lag_days
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_schedule_precedence.py -q`
Expected: FAIL — `AssertionError: EST-002 repite [('EST-001', 'SS'), ('EST-001', 'SS')]`

- [x] **Step 3: Deduplicate**

In `packages/klave_engine/costing/schedule.py`, immediately before the `activities.append(ScheduleActivity(…))` call, insert:

```python
            # The step anchor and the crew tail are frequently the same
            # concept, and each branch appends its own link. Two identical
            # edges are one constraint stated twice: keep the binding lag.
            deduped: dict[tuple[str, str], ScheduleLink] = {}
            for link in links:
                key = (link.predecessor, link.kind)
                current = deduped.get(key)
                if current is None or link.lag_days > current.lag_days:
                    deduped[key] = link
            links = list(deduped.values())
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_schedule_precedence.py -q`
Expected: PASS — 2 passed

- [x] **Step 5: Verify no peso moved**

Run: `.venv/bin/python -m pytest tests/test_gold_money.py tests -q -p no:warnings && .venv/bin/mypy packages/klave_engine`
Expected: all green

- [x] **Step 6: Commit**

```bash
git add packages/klave_engine/costing/schedule.py tests/test_schedule_precedence.py
git commit -m "fix(programa): una restriccion enunciada dos veces era dos aristas"
```

---

## Task 7: Derived concepts take their place in the sequence

> **Verified before writing this task, and it changes the shape:** the catalog
> is *already* spaced by ten — `CIM-001=10, CIM-002=20, EST-001=30, EST-002=40,
> EST-003=50 …`. No re-spacing is needed and `catalog.py`, `steel.py` and
> `formwork.py` need no code change at all. The derived concepts already exist
> as catalog rows; they simply sit in blocks appended at the end of their phase
> — `ACE-*` at 240–245, `EST-008..011` at 344–347, `CIM-006/009` at 332–333 —
> which is exactly why the programa schedules them after every pour. This is a
> pure data migration into the gaps that already exist.
>
> Watch for ties: `CIM-008` and `CIM-010` both sit at 40 today, so any ordering
> read must be deterministic (`ORDER BY sequence_order, code`).

**Files:**
- Modify: `packages/klave_engine/costing/catalog_store.py` (migration v22 + the shared map)
- Test: `tests/test_schedule_precedence.py` (append)

**Interfaces:**
- Produces: `DERIVADO_DE: dict[str, tuple[str, str]]` mapping derived code → `(parent code, "cimbra" | "acero")`. **Task 8 consumes this same map** — one statement of which concept serves which pour, used by both the ordering and the hard edges.

- [x] **Step 1: Write the failing test**

> **Pre-flight ruling R7 — the fixture must be store-backed, or this test is vacuous.**
> I verified this empirically before dispatch. Task 6's `_structural_report()` helper calls
> `generate_cost_report(..., price_book=LIBRO)` with no store, so the catalog is
> `build_default_catalog` alone — which does **not** contain the derived concepts. The
> resulting BoQ holds only `EST-001` and `EST-002`, and the engine says so in its own
> warnings: *"Acero calculado (62 KG) pero el catálogo no tiene el concepto ACE-001 con
> matriz"*. The invariant loop below would `continue` past every single pair and pass while
> the bug is fully present.
>
> The derived concepts live in the **catalog store**, and they need matrices, not just
> concept rows. Add this helper and use it — I ran exactly this shape and it reproduces the
> defect (`EST-008` day 4 vs `EST-001` day 0, inverted):
>
> ```python
> @pytest.fixture
> def store_report(tmp_path):
>     """A report built through a real catalog store.
>
>     The acero and cimbra concepts this test is about are created by
>     apply_steel/apply_formwork against the store's catalog and matrices —
>     build_default_catalog alone has neither, so a store-less fixture produces
>     a two-line BoQ and an invariant that passes by skipping every pair.
>     """
>     from klave_engine.costing.catalog_store import CatalogStore
>     from tests.precios import sembrar
>
>     store = CatalogStore(tmp_path / "catalog.db")
>     sembrar(store)
>     detections = _structural_detections()   # extract from Task 6's helper
>     units = DrawingUnits(unit="m", source="dxf_header", confidence=0.9)
>     return generate_cost_report(
>         "p", detections, units, CostingConfig(), None, None,
>         price_book=store.load_price_book(),
>         store_concepts=store.load_concepts(),
>         apu_templates=store.load_templates(),
>         rendimientos=store.load_rendimientos(),
>     )
> ```
>
> Refactor Task 6's `_structural_report()` so the detection-building half becomes
> `_structural_detections()`, shared by both. Do not change Task 6's existing tests'
> behaviour — they pass today and must keep passing.
>
> **The invariant must also assert it saw something.** After the loop, assert that at least
> one derived/pour pair was actually checked. A `continue`-only pass is the exact failure
> mode this ruling exists to prevent, and without that assertion the next refactor
> reintroduces it silently.

Append to `tests/test_schedule_precedence.py`:

```python
CIMBRA_DE = {"EST-008": "EST-001", "EST-009": "EST-002", "EST-011": "EST-013",
             "CIM-006": "CIM-002", "CIM-009": "CIM-008", "EST-010": "EST-005"}
ACERO_DE = {"ACE-001": "EST-001", "ACE-002": "EST-005", "ACE-003": "CIM-002",
            "ACE-004": "EST-002", "ACE-006": "EST-013"}


def test_nothing_is_poured_before_it_is_formed_or_reinforced():
    """On Marina this failed by 213 days: the programa said pour the columns
    on day 83 and install their formwork on day 296. A cost engineer sees
    that in five seconds, and the document cites RLOPSRM art. 224."""
    report = _structural_report()
    by_code = {a.concept_code: a for a in report.schedule.activities}

    for derived, pour in {**CIMBRA_DE, **ACERO_DE}.items():
        if derived not in by_code or pour not in by_code:
            continue
        assert by_code[derived].start_day <= by_code[pour].start_day, (
            f"{derived} arranca el día {by_code[derived].start_day}, "
            f"después de colar {pour} el día {by_code[pour].start_day}"
        )
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_schedule_precedence.py::test_nothing_is_poured_before_it_is_formed_or_reinforced -q`
Expected: FAIL — `EST-008 arranca el día …, después de colar EST-001 el día …`

- [x] **Step 3: State which concept serves which pour, once**

> **Pre-flight ruling R2 — `DERIVADO_DE` lives in `models.py`, not
> `catalog_store.py`.** Task 8 needs the same map inside `schedule.py`. I
> verified there is no import cycle either way, but pulling the SQLite and
> migration module into the scheduler for one constant is the wrong layering.
> `models.py` is already imported by both `catalog_store.py` and `schedule.py`,
> so the map goes there and both import it from one place.

In `packages/klave_engine/costing/models.py`, at module level (the migration in
Step 4 imports it from there):

```python
# Which derived concept serves which pour, and as what. Task 8's hard edges
# read the same map: one statement of "EST-008 is the formwork for EST-001",
# used both to order it before the pour and to make the pour wait for it.
# You form, you reinforce, you pour — so cimbra takes parent - 2 and acero
# parent - 1, in the gap of nine the catalog already leaves before each parent.
DERIVADO_DE: dict[str, tuple[str, str]] = {
    "EST-008": ("EST-001", "cimbra"),
    "EST-009": ("EST-002", "cimbra"),
    "EST-010": ("EST-005", "cimbra"),
    "EST-011": ("EST-013", "cimbra"),
    "CIM-006": ("CIM-002", "cimbra"),
    "CIM-009": ("CIM-008", "cimbra"),
    "ACE-001": ("EST-001", "acero"),
    "ACE-002": ("EST-005", "acero"),
    "ACE-003": ("CIM-002", "acero"),
    "ACE-004": ("EST-002", "acero"),
    "ACE-005": ("EST-012", "acero"),
    "ACE-006": ("EST-013", "acero"),
}

_OFFSET_POR_TIPO = {"cimbra": -2, "acero": -1}
```

- [x] **Step 4: Add migration v22**

In the same file, following the existing `_migrate_vN` pattern:

```python
    def _migrate_v22(self, conn: sqlite3.Connection) -> None:
        """Put acero and cimbra before the pour they serve.

        They sat in blocks appended at the end of their phase — ACE-* at
        240-245, EST-008..011 at 344-347 — so the programa scheduled the
        formwork for a column 213 days after that column was poured. The
        catalog is already spaced by ten, so each derived concept moves into
        the gap immediately before its parent. Nothing else is reordered.

        Idempotent: the target is computed from the parent's order, which this
        migration never changes, so re-running writes the same values.
        """
        orders = {
            row["code"]: row["sequence_order"]
            for row in conn.execute("SELECT code, sequence_order FROM concepts")
        }
        for code, (parent, tipo) in DERIVADO_DE.items():
            if code not in orders or parent not in orders:
                continue
            conn.execute(
                "UPDATE concepts SET sequence_order = ? WHERE code = ?",
                (orders[parent] + _OFFSET_POR_TIPO[tipo], code),
            )
```

Register it in the migration chain following the `_migrate_v13` pattern (a named method invoked from an inline `if version_row is None or int(version_row["value"]) < N:` block), bumping the stored schema version to **22**. NOTE: the chain already reaches v21 — 14 was taken long ago by a concurrent session. Verify the highest existing version yourself before writing the block.

- [x] **Step 5: Verify the migration on a copy of the real catalog**

```bash
cp data/catalogs/*.db /tmp/klave-migration-check.db
.venv/bin/python -c "
from pathlib import Path
from klave_engine.costing.catalog_store import CatalogStore
import sqlite3
CatalogStore(Path('/tmp/klave-migration-check.db'))
c = sqlite3.connect('/tmp/klave-migration-check.db'); c.row_factory = sqlite3.Row
for r in c.execute(\"SELECT code, sequence_order FROM concepts WHERE phase='Estructura' ORDER BY sequence_order, code\"):
    print(f'{r[\"sequence_order\"]:>5}  {r[\"code\"]}')
"
```

Expected: `EST-008` at 28 and `ACE-001` at 29 immediately before `EST-001` at 30; `EST-009` at 38 and `ACE-004` at 39 before `EST-002` at 40. Run the same command twice and confirm the second run prints identical output — that is the idempotence check.

- [x] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_schedule_precedence.py -q`
Expected: PASS — 3 passed

- [x] **Step 7: Verify no peso moved and the migration is idempotent**

Run: `.venv/bin/python -m pytest tests -q -p no:warnings && .venv/bin/mypy packages/klave_engine`
Expected: all green — in particular `test_gold_money` unchanged, since ordering changes dates and not amounts.

- [x] **Step 8: Commit**

```bash
git add packages/klave_engine/costing/catalog_store.py tests/test_schedule_precedence.py
git commit -m "fix(programa): se cimbra y se arma antes de colar, no 213 dias despues"
```

---

## Task 8: Hard edges where they are real

**Files:**
- Modify: `packages/klave_engine/costing/schedule.py` (forward pass; FS emission)
- Test: `tests/test_schedule_precedence.py` (append)

**Interfaces:**
- Consumes: the `CIMBRA_DE` / `ACERO_DE` relationships from Task 7
- Produces: `ScheduleLink(kind="FS")` for formwork→pour and steel→pour; every other link stays `"SS"`

- [x] **Step 1: Write the failing test**

> **Pre-flight ruling R7 applies here too.** Both tests below must use the store-backed
> `store_report` fixture introduced in Task 7, not `_structural_report()`. Without a store
> the report contains only `EST-001` and `EST-002`, so there are no formwork or steel
> activities to build a hard edge to — `test_the_pour_waits_for_its_formwork_to_finish`
> would fail on its `hard_edges > 0` guard for the wrong reason, and
> `test_the_critical_path_is_not_the_whole_job` would be measuring a two-activity network.

Append to `tests/test_schedule_precedence.py`:

```python
def test_the_pour_waits_for_its_formwork_to_finish():
    """Traslape between trades is correct modelling and stays SS. But you
    cannot pour a column while its formwork is still going up: that pair is
    finish-to-start, and it is the only kind of edge that creates real float
    for everything else."""
    report = _structural_report()
    by_code = {a.concept_code: a for a in report.schedule.activities}

    hard_edges = 0
    for pour_code, pour in by_code.items():
        for link in pour.predecessors:
            if link.kind != "FS":
                continue
            hard_edges += 1
            predecessor = by_code[link.predecessor]
            assert pour.start_day >= predecessor.end_day + link.lag_days
    assert hard_edges > 0, "ninguna arista dura: el colado no espera a nada"


def test_the_critical_path_is_not_the_whole_job():
    """27 of 30 activities critical is the signature of a chain, not a
    network: with only SS lags there is nowhere for float to come from."""
    report = _structural_report()
    activities = report.schedule.activities
    critical = [a for a in activities if a.critical]

    assert len(critical) < len(activities), "todo es ruta crítica: no hay red"
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_schedule_precedence.py -q -k "pour_waits or critical_path"`
Expected: FAIL — `ninguna arista dura: el colado no espera a nada`

- [x] **Step 3: Emit FS for the pairs that cannot overlap**

In `packages/klave_engine/costing/schedule.py`, add near the top — inverting the
map Task 7 defined in `models.py` (pre-flight ruling R2), so which-serves-which
is stated exactly once:

```python
# The pairs that genuinely cannot overlap, derived from the same map that
# orders them. Everything else stays start-to-start with a lag, because
# traslape between trades is how obra actually runs — flattening that would
# replace one wrong model with another.
HARD_PREDECESSORS: dict[str, tuple[str, ...]] = {}
for _derived, (_parent, _tipo) in DERIVADO_DE.items():
    HARD_PREDECESSORS[_parent] = (*HARD_PREDECESSORS.get(_parent, ()), _derived)
```

`DERIVADO_DE` comes from the existing `from klave_engine.costing.models import (...)`
block already at the top of this file — add it to that import list rather than
writing a new import line. Confirm with
`.venv/bin/python -c "import klave_engine.costing.schedule"` after the edit.

In the per-line loop, after the existing SS branches and before the dedup block from Task 6, add:

```python
            for hard_code in HARD_PREDECESSORS.get(line.concept_code, ()):
                placed = next(
                    (a for a in activities if a.concept_code == hard_code), None
                )
                if placed is None:
                    continue
                cursor = max(cursor, placed.end_day)
                links.append(
                    ScheduleLink(predecessor=hard_code, kind="FS", lag_days=0)
                )
```

- [x] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_schedule_precedence.py -q`
Expected: PASS — 5 passed

- [x] **Step 5: Verify no peso moved**

Run: `.venv/bin/python -m pytest tests -q -p no:warnings && .venv/bin/ruff check . && .venv/bin/mypy packages/klave_engine`
Expected: all green

- [x] **Step 6: Commit**

```bash
git add packages/klave_engine/costing/schedule.py tests/test_schedule_precedence.py
git commit -m "feat(programa): el colado espera a su cimbra — aristas duras donde son reales"
```

---

## Task 9: Frentes stops being silent

**Files:**
- Modify: `packages/klave_engine/costing/schedule.py:110-125` (assumption text)
- Modify: `apps/web/app/proyecto/[id]/programa/page.tsx`
- Test: `tests/test_schedule_precedence.py` (append)

**Interfaces:**
- Consumes: `CostingConfig.frentes` and `CostingConfig.crews_per_activity` (both exist, both default `1`)
- Produces: `WorkSchedule.assumptions: list[str]` stating the crew assumption in words

- [x] **Step 1: Write the failing test**

Append to `tests/test_schedule_precedence.py`:

```python
def test_the_programa_states_the_crew_assumption_it_is_making():
    """393 working days for a 546 m² house is what one crew per activity
    produces. There is no honest source to derive a crew count from — the
    plantilla de campo is staffing, not cuadrillas — so the assumption is not
    guessed. It is said out loud, next to the number it produced."""
    report = _structural_report()

    stated = " ".join(report.schedule.assumptions)
    assert "frente" in stated.lower()
    assert "cuadrilla" in stated.lower()
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_schedule_precedence.py::test_the_programa_states_the_crew_assumption_it_is_making -q`
Expected: FAIL — `AttributeError: 'WorkSchedule' object has no attribute 'assumptions'`

- [x] **Step 3: Add the field and state the assumption**

In `packages/klave_engine/costing/models.py`, add to `class WorkSchedule`:

```python
    # The crew assumption in words, because it is the single biggest lever on
    # the plazo and nothing in the drawing can tell us its value.
    assumptions: list[str] = Field(default_factory=list)
```

In `packages/klave_engine/costing/schedule.py`, after constructing `schedule = WorkSchedule(...)`:

```python
    schedule.assumptions.append(
        f"{frentes} frente(s) de trabajo con {max(config.crews_per_activity, 1)} "
        "cuadrilla(s) por actividad. Es el supuesto que más mueve el plazo y el "
        "plano no puede decirlo: ajústalo si la obra tendrá más frentes."
    )
```

- [x] **Step 4: Surface the control**

In `apps/web/app/proyecto/[id]/programa/page.tsx`, beside the `PLAZO CONTRACTUAL` tile, render `costs.schedule.assumptions` as muted text, and add a numeric input bound to the project's `frentes` costing-config value that saves through the existing costing-config endpoint (`PUT /projects/{id}/costing-config`, already used by `CostingConfigForm.tsx` — follow that component's save pattern rather than writing a new one).

Label it `Frentes de trabajo`, help text:

> Cuántos frentes simultáneos tendrá la obra. Un frente con una cuadrilla por actividad es el supuesto por omisión, y es el que produce los plazos largos.

- [x] **Step 5: Run tests and verify types**

Run: `.venv/bin/python -m pytest tests -q -p no:warnings && apps/web/node_modules/.bin/tsc -p apps/web/tsconfig.json --noEmit`
Expected: all green

- [x] **Step 6: Verify in the running app**

Open Marina Lote 04 — Completo → Programa y flujo. Confirm the assumption text renders, and that raising Frentes to 3 shortens the plazo and leaves the presupuesto total unchanged.

- [x] **Step 7: Commit**

```bash
git add packages/klave_engine/costing/models.py packages/klave_engine/costing/schedule.py apps/web/app/proyecto/\[id\]/programa/page.tsx tests/test_schedule_precedence.py
git commit -m "feat(programa): el supuesto de frentes se dice y se ajusta, no se esconde"
```

---

## Task 10: Findings stop drowning their signal

**Files:**
- Modify: `packages/klave_engine/costing/hallazgos.py` (add `HallazgoGrupo`, group in `_summarize`)
- Modify: `apps/web/components/Diagnostico.tsx`
- Test: `tests/test_hallazgos_grouping.py`

**Interfaces:**
- Consumes: `Hallazgo.id` (already `f"sin_precio:{concept_code}"` — the text before `:` is the rule id)
- Produces: `Diagnostico.grupos: list[HallazgoGrupo]` with fields `rule_id: str`, `titulo: str`, `severity: Severity`, `momento: Momento`, `count: int`, `miembros: list[Hallazgo]`, `monto_afectado: float | None`, `exposicion_total: str`

- [x] **Step 1: Write the failing test**

Create `tests/test_hallazgos_grouping.py`:

```python
"""Nineteen findings that differ only in a clave are one finding with a
count. Repeating four identical lines nineteen times is how a reader learns
to skim past warnings — which is the failure mode the severity tiers exist
to prevent."""

from klave_engine.costing.hallazgos import diagnose
from klave_engine.costing.models import (
    BillOfQuantities, BoqLine, CostIntegration, CostReport, QuantityKind, WorkSchedule,
)
from klave_engine.costing.financial import FinancialPlan
from klave_engine.dxf.units import DrawingUnits


def _unpriced(code: str, quantity: float, unit: str) -> BoqLine:
    return BoqLine(
        concept_code=code, description=f"{code} descripción", unit=unit,
        quantity=quantity, unit_price=0.0, amount=0.0, phase="Instalación hidráulica",
        raw_quantity=quantity, raw_kind=QuantityKind.COUNT, source_detection_count=1,
        confidence=0.8, unpriced=True,
    )


def _report_with_unpriced_lines() -> CostReport:
    boq = BillOfQuantities(project_id="p")
    boq.lines = [
        _unpriced("SAN-003", 238.89, "M"),
        _unpriced("HID-007", 1.0, "PZA"),
        _unpriced("SAN-002", 167.75, "M"),
    ]
    return CostReport(
        project_id="p", currency="MXN",
        drawing_units=DrawingUnits(unit="m", source="dxf_header", confidence=0.9),
        boq=boq, apus=[], integration=CostIntegration(), schedule=WorkSchedule(),
        financial=FinancialPlan(),
    )


def test_same_rule_findings_collapse_into_one_group():
    diagnostico = diagnose(_report_with_unpriced_lines())

    sin_precio = next(g for g in diagnostico.grupos if g.rule_id == "sin_precio")
    assert sin_precio.count == 3
    assert len(sin_precio.miembros) == 3
    assert "3" in sin_precio.titulo


def test_groups_rank_by_the_quantity_at_stake_not_alphabetically():
    """SAN-003 at 238 m outranks HID-007 at one pieza."""
    diagnostico = diagnose(_report_with_unpriced_lines())

    sin_precio = next(g for g in diagnostico.grupos if g.rule_id == "sin_precio")
    codes = [h.concept_code for h in sin_precio.miembros]
    assert codes[0] == "SAN-003"
    assert codes[-1] == "HID-007"


def test_a_lone_finding_still_becomes_a_group_of_one():
    """The renderer must handle every finding the same way; a special case for
    singletons is a second code path that will drift."""
    boq = BillOfQuantities(project_id="p")
    boq.lines = [_unpriced("SAN-003", 238.89, "M")]
    report = _report_with_unpriced_lines()
    report.boq = boq

    diagnostico = diagnose(report)

    sin_precio = next(g for g in diagnostico.grupos if g.rule_id == "sin_precio")
    assert sin_precio.count == 1
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_hallazgos_grouping.py -q`
Expected: FAIL — `AttributeError: 'Diagnostico' object has no attribute 'grupos'`

- [x] **Step 3: Add the group model**

In `packages/klave_engine/costing/hallazgos.py`, above `class Diagnostico`:

```python
class HallazgoGrupo(BaseModel):
    """Findings that differ only in which concept they name.

    Nineteen cards repeating the same four lines is not nineteen warnings; it
    is one warning and eighteen distractions, and it buries the finding in the
    group that actually differs.
    """

    rule_id: str
    titulo: str
    severity: Severity
    momento: Momento = "entregar"
    count: int
    miembros: list[Hallazgo] = Field(default_factory=list)
    monto_afectado: float | None = None
    # What is at stake when pesos are genuinely unknowable.
    exposicion_total: str = ""
```

Add to `class Diagnostico`:

```python
    # Findings collapsed by rule; the renderer walks these, not `hallazgos`.
    grupos: list[HallazgoGrupo] = Field(default_factory=list)
```

- [x] **Step 4: Group them**

In `hallazgos.py`, add:

```python
def _agrupar(hallazgos: list[Hallazgo]) -> list[HallazgoGrupo]:
    """One group per rule, members ranked by what each puts at stake."""
    orden: list[str] = []
    por_regla: dict[str, list[Hallazgo]] = {}
    for hallazgo in hallazgos:
        rule_id = hallazgo.id.split(":", 1)[0]
        if rule_id not in por_regla:
            por_regla[rule_id] = []
            orden.append(rule_id)
        por_regla[rule_id].append(hallazgo)

    grupos: list[HallazgoGrupo] = []
    for rule_id in orden:
        miembros = sorted(
            por_regla[rule_id], key=lambda h: -(h.monto_afectado or _cantidad(h))
        )
        primero = miembros[0]
        montos = [h.monto_afectado for h in miembros if h.monto_afectado is not None]
        grupos.append(
            HallazgoGrupo(
                rule_id=rule_id,
                titulo=(
                    primero.title if len(miembros) == 1
                    else f"{len(miembros)} conceptos: {_titulo_de_regla(rule_id)}"
                ),
                severity=primero.severity,
                momento=primero.momento,
                count=len(miembros),
                miembros=miembros,
                monto_afectado=round(sum(montos), 2) if montos else None,
                exposicion_total="; ".join(
                    h.exposicion for h in miembros[:3] if h.exposicion
                ),
            )
        )
    return sorted(grupos, key=lambda g: (SEVERITY_ORDER.get(g.severity, 9), -g.count))


def _cantidad(hallazgo: Hallazgo) -> float:
    """The number inside an exposición ("238.89 M"), for ranking only.

    Never shown as money: it is a quantity, and quantities in different units
    do not compare. It orders members within one rule, where the unit is the
    same kind of thing.
    """
    if not hallazgo.exposicion:
        return 0.0
    head = hallazgo.exposicion.split(" ", 1)[0].replace(",", "")
    try:
        return float(head)
    except ValueError:
        return 0.0


_TITULO_DE_REGLA: dict[str, str] = {
    "sin_precio": "tienen cantidad pero no precio",
}


def _titulo_de_regla(rule_id: str) -> str:
    return _TITULO_DE_REGLA.get(rule_id, rule_id.replace("_", " "))
```

In `_summarize`, set `diagnostico.grupos = _agrupar(hallazgos)` before returning.

- [x] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_hallazgos_grouping.py -q`
Expected: PASS — 3 passed

- [x] **Step 6: Render the groups**

In `apps/web/components/Diagnostico.tsx`, walk `diagnostico.grupos` instead of `diagnostico.hallazgos`. Replace the body of the per-finding `.map(...)` with:

```tsx
{grupo.count === 1 ? (
  <HallazgoCard hallazgo={grupo.miembros[0]} projectId={id} />
) : (
  <div className="finding">
    <div className="flex items-baseline gap-2">
      <h4 className="flex-1">{grupo.titulo}</h4>
      <span className="microlabel">{MOMENTO_LABEL[grupo.momento]}</span>
      {grupo.monto_afectado != null && (
        <span className="tabular-nums">{money(grupo.monto_afectado)}</span>
      )}
    </div>
    {/* The shared explanation renders once. Repeating it per member is what
        turned nineteen findings into a wall a reader learns to skim. */}
    <HallazgoGuidance hallazgo={grupo.miembros[0]} />
    <details>
      <summary>Ver los {grupo.count} conceptos</summary>
      <ul>
        {grupo.miembros.map((h) => (
          <li key={h.id} className="flex justify-between gap-3">
            <span>{h.concept_code ?? h.title}</span>
            {h.exposicion && <span className="tabular-nums">{h.exposicion}</span>}
          </li>
        ))}
      </ul>
    </details>
  </div>
)}
```

`HallazgoCard` and `HallazgoGuidance` are the existing per-finding renderers in
this file. If the current code renders a finding inline rather than through named
components, extract those two first — the singleton path and the group path must
render the same markup, or they will drift.

- [x] **Step 7: Verify in the running app**

Open Marina Lote 04 — Completo → Presupuesto.
Expected: `DINERO FALTANTE` holds a handful of entries, one of which is *"19 conceptos: tienen cantidad pero no precio"*, and *"3 elementos sin armado leído"* is visible without scrolling past boilerplate.

- [x] **Step 8: Commit**

```bash
git add packages/klave_engine/costing/hallazgos.py apps/web/components/Diagnostico.tsx tests/test_hallazgos_grouping.py
git commit -m "fix(hallazgos): diecinueve tarjetas iguales son un hallazgo con cuenta"
```

---

## Task 11: Counts live with the project

**Files:**
- Create: `packages/klave_engine/costing/conteos.py`
- Modify: `apps/api/routes/reviews.py` (two endpoints)
- Modify: `packages/klave_engine/evals/recall_cli.py`
- Test: `tests/test_conteos.py`

**Interfaces:**
- Consumes: `ConteoDeObra` / `ConteoHumano` from `klave_engine.evals.recall`
- Produces: `load_conteos(control_dir) -> ConteosDeProyecto`, `save_conteos(control_dir, conteos)`, `ConteosDeProyecto.a_conteo_de_obra(drawing_id) -> ConteoDeObra`; endpoints `GET/PUT /projects/{id}/conteos`

- [x] **Step 1: Write the failing test**

Create `tests/test_conteos.py`:

```python
"""Human counts are per-project human data, like reviews — they belong beside
them, not in a repo path a deployed server cannot write. The count that
matters most is for a family the engine never detected: those never appear in
a template generated from detections, and they are the expensive ones."""

from klave_engine.costing.conteos import ConteoHoja, ConteosDeProyecto, load_conteos, save_conteos


def test_counts_round_trip_through_the_project_store(tmp_path):
    conteos = ConteosDeProyecto(
        contado_por="Diego Gaytán",
        hojas=[
            ConteoHoja(hoja="E-02", familia="castillo", dibujados=118, detectados=118),
            ConteoHoja(hoja="E-02", familia="escalera", dibujados=2, detectados=0),
        ],
    )

    save_conteos(tmp_path, conteos)
    again = load_conteos(tmp_path)

    assert again.contado_por == "Diego Gaytán"
    assert len(again.hojas) == 2


def test_a_family_the_engine_never_saw_survives_the_round_trip(tmp_path):
    """If this is lost, the measurement cannot see its own blind spot."""
    save_conteos(
        tmp_path,
        ConteosDeProyecto(
            hojas=[ConteoHoja(hoja="E-02", familia="escalera", dibujados=2, detectados=0)]
        ),
    )

    escalera = next(h for h in load_conteos(tmp_path).hojas if h.familia == "escalera")

    assert escalera.dibujados == 2
    assert escalera.detectados == 0


def test_sheets_fold_into_one_count_per_family(tmp_path):
    """Recall is measured per family across the whole obra; counting happens
    per sheet because that is how a person reads a plan."""
    conteos = ConteosDeProyecto(
        hojas=[
            ConteoHoja(hoja="E-01", familia="castillo", dibujados=60, detectados=58),
            ConteoHoja(hoja="E-02", familia="castillo", dibujados=58, detectados=56),
        ]
    )

    obra = conteos.a_conteo_de_obra("marina")

    castillo = next(c for c in obra.conteos if c.familia == "castillo")
    assert castillo.dibujados == 118


def test_missing_file_is_an_empty_count_not_an_error(tmp_path):
    assert load_conteos(tmp_path).hojas == []


def test_reviewing_a_project_promotes_its_gold_entry_past_baseline(tmp_path):
    """The promotion machinery has been complete since gold.py:305 and has
    been waiting for reviews that never came: every detection_reviews.json in
    the repo has zero decisions. This is the assertion that the loop closes —
    a reviewed project stops being a regression guard and starts being truth."""
    from klave_engine.costing.reviews import DetectionReview, ProjectReviews, save_reviews

    reviews = ProjectReviews()
    reviews.detections["C-1"] = DetectionReview(status="confirmed")
    reviews.detections["C-2"] = DetectionReview(status="excluded")
    save_reviews(tmp_path, reviews)

    from klave_engine.costing.reviews import load_reviews

    loaded = load_reviews(tmp_path)
    confirmed = sorted(k for k, r in loaded.detections.items() if r.status == "confirmed")
    excluded = sorted(k for k, r in loaded.detections.items() if r.status == "excluded")

    # These two lists are exactly what gold.capture reads to choose "partial"
    # over "baseline" (gold.py:293-310).
    assert confirmed == ["C-1"]
    assert excluded == ["C-2"]
    assert loaded.verification.detections_confirmed_at is None  # partial, not verified
```

Read `packages/klave_engine/costing/reviews.py` for the exact `DetectionReview` constructor and the name of the save helper (`save_reviews` or equivalent) — match it rather than assuming.

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_conteos.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'klave_engine.costing.conteos'`

- [x] **Step 3: Write the module**

Create `packages/klave_engine/costing/conteos.py`:

```python
"""What a person counted on the plan, stored beside what they reviewed.

Counting used to mean hand-editing a JSON file in the repo, which a deployed
server cannot write and a cost engineer will not do. These live in the
project's control dir next to detection_reviews.json, because they are the
same kind of thing: a human's judgement about this drawing.
"""

from pathlib import Path

from pydantic import BaseModel, Field

from klave_engine.common.io import read_json, write_json
from klave_engine.evals.recall import ConteoDeObra, ConteoHumano

CONTEOS_FILENAME = "conteos.json"


class ConteoHoja(BaseModel):
    """One family counted on one sheet."""

    hoja: str
    familia: str
    # What the person counted on the sheet.
    dibujados: int = 0
    # What the engine found there, carried for context at counting time.
    detectados: int = 0
    nota: str = ""


class ConteosDeProyecto(BaseModel):
    contado_por: str = ""
    contado_en: str = ""
    hojas: list[ConteoHoja] = Field(default_factory=list)

    def a_conteo_de_obra(self, drawing_id: str) -> ConteoDeObra:
        """Fold the per-sheet counts into the per-family shape recall measures.

        Counting is per sheet because that is how a person reads a plan;
        recall is per family because that is how a detector fails.
        """
        totales: dict[str, int] = {}
        for hoja in self.hojas:
            totales[hoja.familia] = totales.get(hoja.familia, 0) + hoja.dibujados
        return ConteoDeObra(
            drawing_id=drawing_id,
            contado_por=self.contado_por,
            contado_en=self.contado_en,
            conteos=[
                ConteoHumano(familia=familia, dibujados=dibujados)
                for familia, dibujados in sorted(totales.items())
            ],
        )


def load_conteos(control_dir: Path) -> ConteosDeProyecto:
    path = control_dir / CONTEOS_FILENAME
    if not path.exists():
        return ConteosDeProyecto()
    return ConteosDeProyecto.model_validate(read_json(path))


def save_conteos(control_dir: Path, conteos: ConteosDeProyecto) -> None:
    control_dir.mkdir(parents=True, exist_ok=True)
    write_json(control_dir / CONTEOS_FILENAME, conteos)
```

If `ConteoDeObra` or `ConteoHumano` are dataclasses rather than pydantic models, construct them with plain keyword arguments — read `packages/klave_engine/evals/recall.py:40-60` and match its constructor exactly.

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_conteos.py -q`
Expected: PASS — 4 passed

- [x] **Step 5: Add the endpoints**

In `apps/api/routes/reviews.py`, following the shape of the existing review endpoints (same auth, same `project_recompute_lock`, same event broadcast — but **no recompute**, since counts change no number):

```python
@router.get("/{project_id}/conteos")
def get_conteos(
    project_id: str,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    control_dir = store.get_root(project_id) / settings.processed_dir_name
    return load_conteos(control_dir).model_dump()


@router.put("/{project_id}/conteos")
def put_conteos(
    project_id: str,
    body: ConteosDeProyecto,
    x_actor: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Counts change no number, so nothing recomputes — they are evidence
    about the engine, not input to it."""
    control_dir = store.get_root(project_id) / settings.processed_dir_name
    with project_recompute_lock(project_id):
        body.contado_por = body.contado_por or clean_actor(x_actor) or ""
        save_conteos(control_dir, body)
    return body.model_dump()
```

- [x] **Step 6: Teach recall_cli to read the project store**

In `packages/klave_engine/evals/recall_cli.py`, in the `medir` branch, look for `<project_root>/processed/conteos.json` first and fall back to `evals/conteos/<project_id>.json`:

```python
    control_dir = _project_root(project_id) / "processed"
    conteos_de_proyecto = load_conteos(control_dir)
    if conteos_de_proyecto.hojas:
        conteo = conteos_de_proyecto.a_conteo_de_obra(project_id)
    else:
        conteo = ConteoDeObra.desde_json(Path("evals/conteos") / f"{project_id}.json")
```

- [x] **Step 7: Verify the whole suite**

Run: `.venv/bin/python -m pytest tests -q -p no:warnings && .venv/bin/ruff check . && .venv/bin/mypy packages/klave_engine`
Expected: all green

- [x] **Step 8: Commit**

```bash
git add packages/klave_engine/costing/conteos.py packages/klave_engine/evals/recall_cli.py apps/api/routes/reviews.py tests/test_conteos.py
git commit -m "feat(medicion): los conteos humanos viven junto a las revisiones del proyecto"
```

---

## Task 12: Counting becomes an input

**Files:**
- Modify: `apps/web/app/proyecto/[id]/revision/page.tsx`
- Modify: `apps/web/lib/api.ts` (`getConteos`, `putConteos`)

**Interfaces:**
- Consumes: `GET/PUT /projects/{id}/conteos` (Task 11); the AI coverage comparison already computed by `klave_engine.llm.coverage.coverage_flags`

- [x] **Step 1: Add the client functions**

In `apps/web/lib/api.ts`, following the existing typed-client pattern:

```typescript
export type ConteoHoja = {
  hoja: string;
  familia: string;
  dibujados: number;
  detectados: number;
  nota: string;
};

export type ConteosDeProyecto = {
  contado_por: string;
  contado_en: string;
  hojas: ConteoHoja[];
};

export const getConteos = (id: string) =>
  getJSON<ConteosDeProyecto>(`/projects/${id}/conteos`);

export const putConteos = (id: string, body: ConteosDeProyecto, actor?: string) =>
  putJSON<ConteosDeProyecto>(`/projects/${id}/conteos`, body, actor);
```

`getJSON` and `putJSON` are the module-private helpers at the top of `api.ts`
(`putJSON` at line 70); every exported client function in the file is built on
them — `putIndices` at line 1626 is the closest shape to copy, including how it
threads `actor`.

- [x] **Step 2: Add the counting section**

In `apps/web/app/proyecto/[id]/revision/page.tsx`, add a section below the existing review list:

```tsx
<Card>
  <h3>Cuántos hay dibujados</h3>
  <p className="text-muted">
    El motor se compara contra sí mismo en todo lo demás. Esto es lo único que
    dice cuánto de lo dibujado encuentra, y sólo lo puede contestar alguien
    contando.
  </p>

  <table>
    <thead>
      <tr><th>Hoja</th><th>Familia</th><th>Detectados</th><th>Dibujados</th></tr>
    </thead>
    <tbody>
      {filas.map((fila) => (
        <tr key={`${fila.hoja}:${fila.familia}`}>
          <td>{fila.hoja}</td>
          <td>{FAMILY_LABEL[fila.familia] ?? fila.familia}</td>
          <td className="tabular-nums text-muted">{fila.detectados}</td>
          <td>
            <input
              type="number"
              min={0}
              className="tabular-nums"
              defaultValue={fila.dibujados || undefined}
              onBlur={(e) => guardar({ ...fila, dibujados: Number(e.target.value) || 0 })}
            />
          </td>
        </tr>
      ))}
    </tbody>
  </table>

  <div className="border-t pt-3">
    <p className="text-muted">
      Lo más importante son las familias que no aparecen arriba. Si el plano
      tiene escaleras y el motor no detectó ninguna, ese renglón lo escribes tú:
      es el que cuesta más caro descubrir tarde.
    </p>
    <div className="flex gap-2">
      <Select value={nuevaHoja} onChange={setNuevaHoja}>
        {hojas.map((h) => <option key={h} value={h}>{h}</option>)}
      </Select>
      <Select value={nuevaFamilia} onChange={setNuevaFamilia}>
        {FAMILIAS.map((f) => (
          <option key={f} value={f}>{FAMILY_LABEL[f] ?? f}</option>
        ))}
      </Select>
      <input type="number" min={0} value={nuevaCuenta}
             onChange={(e) => setNuevaCuenta(Number(e.target.value) || 0)} />
      <Button onClick={() => guardar({
        hoja: nuevaHoja, familia: nuevaFamilia,
        dibujados: nuevaCuenta, detectados: 0, nota: "",
      })}>
        Agregar
      </Button>
    </div>
  </div>
</Card>
```

Build `filas` by joining, per sheet, each family the engine detected there with any saved `ConteoHoja`, pre-filling `dibujados` from the AI sheet-read count when `coverage_flags` supplied one for that sheet and family, otherwise leaving it empty (never pre-filled from the engine's own count — a number the reader only has to accept is a number they will accept).

`guardar` merges one `ConteoHoja` into the loaded `ConteosDeProyecto` (replacing any row with the same `hoja` + `familia`) and calls `putConteos`. `FAMILIAS` is the 21 values of `Family` from `klave_engine.detection.taxonomy`; the web already maps family keys to Spanish labels in `lib/families.ts` — reuse that rather than adding a second table.

- [x] **Step 3: Verify types**

Run: `apps/web/node_modules/.bin/tsc -p apps/web/tsconfig.json --noEmit`
Expected: exit 0

- [x] **Step 4: Verify in the running app**

Open Marina Lote 04 — Estructural → Revisión. Enter a count for `castillo`, add `escalera` with a count of 2, reload, and confirm both persist.

Then run: `.venv/bin/python -m klave_engine.evals.recall_cli medir marina_lote_04_estructural_d1cd5ec8`
Expected: a recall table reading the counts entered in the app, with `escalera` showing recall 0.00 and a Wilson interval.

- [x] **Step 5: Commit**

```bash
git add apps/web
git commit -m "feat(revision): contar lo dibujado deja de ser editar un JSON a mano"
```

---

## Task 13: The ritual, written down

**Files:**
- Modify: `docs/evals.md`, `docs/recall.md`, `docs/principios-de-interfaz.md`

- [x] **Step 1: Document the loop in `docs/evals.md`**

Add a section **El lazo completo**:

> Un gold set compara al motor contra sí mismo. Para que diga algo sobre exactitud necesita decisiones humanas, y la forma de tomarlas es usar el producto:
>
> 1. Revisa un proyecto en la app — confirma y excluye detecciones en *Revisión*. Eso ejercita el lazo de corrección y produce la verdad al mismo tiempo.
> 2. `make gold-capture ROOT=data/uploads/<proyecto> ID=<drawing-id>` — la entrada pasa sola de `baseline` a `partial`.
> 3. Cuenta lo que falta en *Revisión → Cuántos hay dibujados*, agregando las familias que el motor no detectó.
> 4. `uv run python -m klave_engine.evals.recall_cli medir <project_id>`.
>
> Para promover una cantidad a verdad humana, cuantifícala a mano y cambia su `source` de `engine` a `human` en `evals/gold/<id>.json`, con una tolerancia estrecha y una nota que diga cómo se cuantificó.

- [x] **Step 2: Update `docs/recall.md`**

Replace the `plantilla` instructions with the in-app flow, and state that counts now live in `<proyecto>/processed/conteos.json`, with `evals/conteos/` kept as the local fallback. Leave the methodology sections — Wilson intervals, money weighting, the fifteen-to-twenty-drawing sample — unchanged; they were already right.

- [x] **Step 3: Update `docs/principios-de-interfaz.md`**

Under **I. Honestidad**, add:

> ### 3. El veredicto se decide una vez
>
> Si un número puede mostrarse como dinero lo decide `costing/presentation.py` y nadie más. La regla vivía en tres pantallas con tres niveles de rigor, y la más nueva siempre heredaba el más débil: la lista de proyectos llegó a mostrar $768,759,055 de una obra cuyo presupuesto se negaba a mostrar un peso. Una regla que se vuelve a deducir en cada superficie es una regla que se degrada con cada superficie.

- [x] **Step 4: Full verification**

Run: `.venv/bin/python -m pytest tests -q -p no:warnings && .venv/bin/ruff check . && .venv/bin/mypy packages/klave_engine && apps/web/node_modules/.bin/tsc -p apps/web/tsconfig.json --noEmit && make eval-gold && make eval-demo`
Expected: all green, `test_gold_money` unchanged

- [x] **Step 5: Commit**

```bash
git add docs/
git commit -m "docs: el lazo de medicion, y por que el veredicto se decide una sola vez"
```

---

## Definition of done

- [x] Torre Reforma's row reads **sin unidades**; no surface shows a total the presupuesto withholds
- [x] No cimbra or acero activity starts after the pour it serves, on any project
- [x] No activity lists the same predecessor twice
- [x] Critical-path share is below 27/30 on Marina, and the programa states its crew assumption
- [x] The presupuesto shows confidence bands, not a single pass rate
- [x] `DINERO FALTANTE` shows one grouped entry, not nineteen identical cards
- [x] Counting a family happens in the app and `recall_cli medir` reads it
- [x] **`test_gold_money` passes unchanged** — no peso moved in this round
- [x] `ruff`, `mypy`, `tsc`, `make eval-gold`, `make eval-demo` all green
