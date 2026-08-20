"""Workspace catalog database: insumos, APU matrices, and rendimientos.

The reference values in ``insumos.py`` seed a SQLite database on first use;
after that the database is the source of truth the user owns and edits. Every
insumo row carries a free-text ``source`` so a price is never anonymous:
"Referencia Klave" until the user replaces it with their own quotation.

Concept definitions (detection→quantity rules) remain code: they are bound to
the detector implementations. What the user owns here is the pricing data —
insumo costs, APU component matrices, and production rates (rendimientos).
"""

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from klave_engine.common.logging import get_logger, log_stage
from klave_engine.costing.catalog import build_default_catalog
from klave_engine.costing.insumos import APU_TEMPLATES, RESOURCES
from klave_engine.costing.models import CostingAssumptions, Resource, ResourceType

logger = get_logger(__name__)

CATALOG_DB_FILENAME = "catalog.db"
SEED_SOURCE = "Referencia Klave"

_LOCK = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS insumos (
    code TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    unit TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    unit_cost REAL NOT NULL,
    is_labor_percentage INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS apu_components (
    concept_code TEXT NOT NULL,
    resource_code TEXT NOT NULL,
    quantity REAL NOT NULL,
    PRIMARY KEY (concept_code, resource_code)
);
CREATE TABLE IF NOT EXISTS concept_settings (
    concept_code TEXT PRIMARY KEY,
    production_rate_per_day REAL
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


class CatalogStore:
    """SQLite-backed workspace catalog. Connections are per-operation and a
    process-wide lock serializes writers (usage is low-frequency UI edits)."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK, self._connect() as conn:
            conn.executescript(_SCHEMA)
            seeded = conn.execute(
                "SELECT value FROM meta WHERE key = 'seeded'"
            ).fetchone()
            if seeded is None:
                self._seed(conn)
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('seeded', ?)", (_now(),)
                )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _seed(self, conn: sqlite3.Connection) -> None:
        for resource in RESOURCES.values():
            conn.execute(
                "INSERT INTO insumos (code, description, unit, resource_type, "
                "unit_cost, is_labor_percentage, source, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    resource.code,
                    resource.description,
                    resource.unit,
                    resource.resource_type.value,
                    resource.unit_cost,
                    int(resource.is_labor_percentage),
                    SEED_SOURCE,
                    _now(),
                ),
            )
        for concept_code, components in APU_TEMPLATES.items():
            for resource_code, quantity in components:
                conn.execute(
                    "INSERT INTO apu_components (concept_code, resource_code, quantity) "
                    "VALUES (?, ?, ?)",
                    (concept_code, resource_code, quantity),
                )
        for concept in build_default_catalog(CostingAssumptions()):
            conn.execute(
                "INSERT INTO concept_settings (concept_code, production_rate_per_day) "
                "VALUES (?, ?)",
                (concept.code, concept.production_rate_per_day),
            )
        log_stage(logger, "catalog_seeded", db_path=str(self.db_path))

    # ---------------------------------------------------------------- reads

    def load_price_book(self) -> dict[str, Resource]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM insumos ORDER BY code").fetchall()
        return {
            row["code"]: Resource(
                code=row["code"],
                description=row["description"],
                unit=row["unit"],
                unit_cost=row["unit_cost"],
                resource_type=ResourceType(row["resource_type"]),
                is_labor_percentage=bool(row["is_labor_percentage"]),
            )
            for row in rows
        }

    def load_templates(self) -> dict[str, list[tuple[str, float]]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT concept_code, resource_code, quantity FROM apu_components "
                "ORDER BY concept_code, resource_code"
            ).fetchall()
        templates: dict[str, list[tuple[str, float]]] = {}
        for row in rows:
            templates.setdefault(row["concept_code"], []).append(
                (row["resource_code"], row["quantity"])
            )
        return templates

    def load_rendimientos(self) -> dict[str, float]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT concept_code, production_rate_per_day FROM concept_settings"
            ).fetchall()
        return {
            row["concept_code"]: row["production_rate_per_day"]
            for row in rows
            if row["production_rate_per_day"] is not None
        }

    def list_insumos(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM insumos ORDER BY code").fetchall()
        return [dict(row) for row in rows]

    # --------------------------------------------------------------- writes

    def upsert_insumo(
        self,
        code: str,
        *,
        description: str | None = None,
        unit: str | None = None,
        resource_type: str | None = None,
        unit_cost: float | None = None,
        source: str | None = None,
    ) -> dict:
        """Update an existing insumo, or create one when all fields are given."""
        with _LOCK, self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM insumos WHERE code = ?", (code,)
            ).fetchone()
            if existing is None:
                if not (description and unit and resource_type and unit_cost is not None):
                    raise ValueError(
                        "Creating an insumo requires description, unit, "
                        "resource_type, and unit_cost."
                    )
                ResourceType(resource_type)  # validates
                conn.execute(
                    "INSERT INTO insumos (code, description, unit, resource_type, "
                    "unit_cost, is_labor_percentage, source, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, 0, ?, ?)",
                    (code, description, unit, resource_type, unit_cost, source or "", _now()),
                )
            else:
                conn.execute(
                    "UPDATE insumos SET description = ?, unit = ?, resource_type = ?, "
                    "unit_cost = ?, source = ?, updated_at = ? WHERE code = ?",
                    (
                        description if description is not None else existing["description"],
                        unit if unit is not None else existing["unit"],
                        resource_type
                        if resource_type is not None
                        else existing["resource_type"],
                        unit_cost if unit_cost is not None else existing["unit_cost"],
                        source if source is not None else existing["source"],
                        _now(),
                        code,
                    ),
                )
            row = conn.execute("SELECT * FROM insumos WHERE code = ?", (code,)).fetchone()
        return dict(row)

    def set_apu_components(
        self, concept_code: str, components: list[tuple[str, float]]
    ) -> None:
        """Replace one concept's APU matrix. Every resource must exist and every
        quantity must be positive; the matrix must not be empty."""
        if not components:
            raise ValueError("An APU needs at least one component.")
        book = self.load_price_book()
        for resource_code, quantity in components:
            if resource_code not in book:
                raise ValueError(f"Unknown resource {resource_code}.")
            if quantity <= 0:
                raise ValueError(f"Quantity for {resource_code} must be positive.")
        with _LOCK, self._connect() as conn:
            conn.execute(
                "DELETE FROM apu_components WHERE concept_code = ?", (concept_code,)
            )
            for resource_code, quantity in components:
                conn.execute(
                    "INSERT INTO apu_components (concept_code, resource_code, quantity) "
                    "VALUES (?, ?, ?)",
                    (concept_code, resource_code, quantity),
                )

    def set_rendimiento(self, concept_code: str, production_rate_per_day: float) -> None:
        if production_rate_per_day <= 0:
            raise ValueError("El rendimiento debe ser positivo.")
        with _LOCK, self._connect() as conn:
            conn.execute(
                "INSERT INTO concept_settings (concept_code, production_rate_per_day) "
                "VALUES (?, ?) ON CONFLICT(concept_code) "
                "DO UPDATE SET production_rate_per_day = excluded.production_rate_per_day",
                (concept_code, production_rate_per_day),
            )

    def import_prices(
        self, rows: list[dict[str, str]], source: str
    ) -> dict[str, list[str] | int]:
        """Bulk price update from CSV rows ({code, unit_cost}). Only existing
        codes are updated — imports never invent catalog structure silently."""
        updated = 0
        skipped: list[str] = []
        with _LOCK, self._connect() as conn:
            for row in rows:
                code = (row.get("code") or row.get("clave") or "").strip()
                raw_cost = (row.get("unit_cost") or row.get("costo_unitario") or "").strip()
                if not code or not raw_cost:
                    skipped.append(code or "(sin clave)")
                    continue
                try:
                    unit_cost = float(raw_cost.replace(",", "").replace("$", ""))
                except ValueError:
                    skipped.append(code)
                    continue
                if unit_cost <= 0:
                    skipped.append(code)
                    continue
                result = conn.execute(
                    "UPDATE insumos SET unit_cost = ?, source = ?, updated_at = ? "
                    "WHERE code = ?",
                    (unit_cost, source, _now(), code),
                )
                if result.rowcount:
                    updated += 1
                else:
                    skipped.append(code)
        log_stage(
            logger, "catalog_prices_imported", updated=updated, skipped=len(skipped)
        )
        return {"updated": updated, "skipped": skipped}


_STORES: dict[Path, CatalogStore] = {}


def get_catalog_store(data_dir: Path) -> CatalogStore:
    path = (data_dir / CATALOG_DB_FILENAME).resolve()
    with _LOCK:
        store = _STORES.get(path)
    if store is None:
        store = CatalogStore(path)
        with _LOCK:
            _STORES[path] = store
    return store
