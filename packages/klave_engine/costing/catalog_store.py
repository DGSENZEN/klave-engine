"""Workspace catalog database: insumos, APU matrices, and rendimientos.

The reference values in ``insumos.py`` seed a SQLite database on first use;
after that the database is the source of truth the user owns and edits. Every
insumo row carries a free-text ``source`` so a price is never anonymous:
"Referencia Klave" until the user replaces it with their own quotation.

Concept definitions (detection→quantity rules) remain code: they are bound to
the detector implementations. What the user owns here is the pricing data —
insumo costs, APU component matrices, and production rates (rendimientos).
"""

import json
import sqlite3
import threading
from collections.abc import Iterable
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
    source_type TEXT NOT NULL DEFAULT 'referencia',
    region TEXT NOT NULL DEFAULT 'MX-CMX',
    vigencia TEXT NOT NULL DEFAULT '',
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
CREATE TABLE IF NOT EXISTS concepts (
    code TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    unit TEXT NOT NULL,
    phase TEXT NOT NULL,
    production_rate_per_day REAL NOT NULL,
    rule_key TEXT,
    sequence_order INTEGER NOT NULL DEFAULT 100,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS price_sources (
    source_key TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    publisher TEXT NOT NULL DEFAULT '',
    region TEXT NOT NULL DEFAULT 'MX',
    vigencia TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT 'precios_unitarios',
    url TEXT NOT NULL DEFAULT '',
    sha256 TEXT,
    imported_at TEXT NOT NULL,
    row_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS reference_prices (
    ref_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key TEXT NOT NULL REFERENCES price_sources(source_key) ON DELETE CASCADE,
    clave TEXT NOT NULL,
    description TEXT NOT NULL,
    unit TEXT NOT NULL,
    price REAL NOT NULL,
    group_clave TEXT NOT NULL DEFAULT '',
    group_description TEXT NOT NULL DEFAULT '',
    extra TEXT,
    page INTEGER
);
CREATE INDEX IF NOT EXISTS reference_prices_source_clave
    ON reference_prices (source_key, clave);
CREATE TABLE IF NOT EXISTS insumo_analysis (
    code TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    params TEXT NOT NULL,
    result TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workspace_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

SEED_VIGENCIA = "2026-08"

# Reference basket beyond the original seven-concept core: standard Mexican
# obra-negra practice values, all explicitly labeled reference data — a
# runnable baseline to replace with quotations, never a market claim.
EXTRA_RESOURCES: list[tuple[str, str, str, float, str]] = [
    ("MAT-CEM", "Cemento gris CPC 30R", "TON", 3350.0, "material"),
    ("MAT-ARENA", "Arena de mina", "M3", 420.0, "material"),
    ("MAT-GRAVA", "Grava triturada 3/4\"", "M3", 460.0, "material"),
    ("MAT-AGUA", "Agua para obra", "M3", 35.0, "material"),
    ("MAT-CONC150", "Concreto hecho en obra f'c=150 kg/cm²", "M3", 2100.0, "material"),
    ("MAT-MALLA", "Malla electrosoldada 6x6-10/10", "M2", 85.0, "material"),
    ("MAT-ALAMBRE", "Alambre recocido", "KG", 38.0, "material"),
    ("MAT-CLAVO", "Clavo para cimbra", "KG", 42.0, "material"),
    ("MAT-MADERA", "Madera de pino 3a para obra", "PT", 28.0, "material"),
    ("MAT-TEPETATE", "Tepetate para relleno", "M3", 260.0, "material"),
    ("MO-OF-ALB", "Oficial albañil", "JOR", 1050.0, "mano_de_obra"),
    ("MO-AYUD", "Ayudante general", "JOR", 700.0, "mano_de_obra"),
    ("EQ-BAILARINA", "Compactador tipo bailarina", "JOR", 650.0, "equipo"),
    ("EQ-CAMION", "Camión de volteo 7 m³ (viaje)", "VJE", 950.0, "equipo"),
]

# Manual concepts: priced through their APU, quantified only by documented
# adjustments or viewer measurements — the estimator's own takeoff.
# Acero de refuerzo: resources and concepts the steel stage prices. Labor
# here is a reference rate (replace it by applying salario real).
STEEL_RESOURCES: list[tuple[str, str, str, float, str]] = [
    ("MAT-ALAMBRE", "Alambre recocido cal. 18", "KG", 34.0, "material"),
    ("MAT-MALLA66", "Malla electrosoldada 6x6-10/10", "M2", 62.0, "material"),
    ("MO-FIERRERO", "Fierrero (oficial)", "JOR", 830.0, "mano_de_obra"),
]
STEEL_CONCEPTS: list[tuple[str, str, str, str, float, int, list[tuple[str, float]]]] = [
    ("ACE-001", "Acero de refuerzo fy=4200 kg/cm² en castillos y columnas, habilitado y armado",
     "KG", "Estructura", 180.0, 40,
     [("MAT-ACERO", 0.00104), ("MAT-ALAMBRE", 0.02), ("MO-FIERRERO", 0.0065),
      ("MO-AYUD", 0.0065), ("EQ-HERRAMIENTA", 1.0)]),
    ("ACE-002", "Acero de refuerzo fy=4200 kg/cm² en dalas y cerramientos, habilitado y armado",
     "KG", "Estructura", 200.0, 41,
     [("MAT-ACERO", 0.00104), ("MAT-ALAMBRE", 0.02), ("MO-FIERRERO", 0.006),
      ("MO-AYUD", 0.006), ("EQ-HERRAMIENTA", 1.0)]),
    ("ACE-003", "Acero de refuerzo fy=4200 kg/cm² en zapatas (parrilla), habilitado y armado",
     "KG", "Cimentación", 220.0, 31,
     [("MAT-ACERO", 0.00104), ("MAT-ALAMBRE", 0.02), ("MO-FIERRERO", 0.0055),
      ("MO-AYUD", 0.0055), ("EQ-HERRAMIENTA", 1.0)]),
    ("ACE-004", "Acero de refuerzo fy=4200 kg/cm² en trabes, habilitado y armado",
     "KG", "Estructura", 180.0, 42,
     [("MAT-ACERO", 0.00104), ("MAT-ALAMBRE", 0.02), ("MO-FIERRERO", 0.0065),
      ("MO-AYUD", 0.0065), ("EQ-HERRAMIENTA", 1.0)]),
    ("ACE-005", "Malla electrosoldada 6x6-10/10 en capa de compresión de losa, con traslapes",
     "M2", "Estructura", 250.0, 43,
     [("MAT-MALLA66", 1.0), ("MAT-ALAMBRE", 0.01), ("MO-FIERRERO", 0.004),
      ("MO-AYUD", 0.004), ("EQ-HERRAMIENTA", 1.0)]),
]

EXTRA_CONCEPTS: list[tuple[str, str, str, str, float, int, list[tuple[str, float]]]] = [
    (
        "CIM-003", "Plantilla de concreto f'c=100 kg/cm², 5 cm", "M2",
        "Cimentación", 80.0, 30,
        [("MAT-CONC150", 0.055), ("MO-CUAD-ALB", 0.060), ("EQ-HERRAMIENTA", 1.0)],
    ),
    (
        "CIM-004", "Relleno compactado con tepetate en capas de 20 cm", "M3",
        "Cimentación", 25.0, 40,
        [
            ("MAT-TEPETATE", 1.25), ("MAT-AGUA", 0.15), ("MO-AYUD", 0.35),
            ("EQ-BAILARINA", 0.12), ("EQ-HERRAMIENTA", 1.0),
        ],
    ),
    (
        "CIM-005", "Acarreo de material producto de excavación fuera de obra", "M3",
        "Cimentación", 40.0, 50,
        [("MO-AYUD", 0.12), ("EQ-CAMION", 0.14), ("EQ-HERRAMIENTA", 1.0)],
    ),
    (
        "EST-005", "Cadena o dala de concreto armado 15x20 cm", "M",
        "Estructura", 18.0, 40,
        [
            ("MAT-CONC150", 0.033), ("MAT-ACERO", 0.0045), ("MAT-CIMBRA", 0.42),
            ("MO-CUAD-ALB", 0.12), ("MO-CUAD-FIE", 0.08), ("EQ-HERRAMIENTA", 1.0),
        ],
    ),
    (
        "EST-006", "Castillo ahogado en block con armex 15x15", "M",
        "Estructura", 22.0, 50,
        [
            ("MAT-CONC150", 0.023), ("MAT-ACERO", 0.0035),
            ("MO-CUAD-ALB", 0.10), ("EQ-HERRAMIENTA", 1.0),
        ],
    ),
    (
        "EST-007", "Firme de concreto de 8 cm f'c=150 con malla", "M2",
        "Estructura", 45.0, 60,
        [
            ("MAT-CONC150", 0.085), ("MAT-MALLA", 1.05),
            ("MO-CUAD-ALB", 0.09), ("EQ-HERRAMIENTA", 1.0),
        ],
    ),
]


def _now() -> str:
    return datetime.now(UTC).isoformat()


class CatalogStore:
    """SQLite-backed workspace catalog. Connections are per-operation and a
    process-wide lock serializes writers (usage is low-frequency UI edits)."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK, self._connect() as conn:
            # Existing v1 databases predate the provenance columns; ALTER
            # before executing the full schema so both paths converge.
            existing = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='insumos'"
            ).fetchone()
            if existing is not None:
                columns = {
                    row["name"]
                    for row in conn.execute("PRAGMA table_info(insumos)").fetchall()
                }
                for column, definition in (
                    ("source_type", "TEXT NOT NULL DEFAULT 'referencia'"),
                    ("region", "TEXT NOT NULL DEFAULT 'MX-CMX'"),
                    ("vigencia", "TEXT NOT NULL DEFAULT ''"),
                ):
                    if column not in columns:
                        conn.execute(f"ALTER TABLE insumos ADD COLUMN {column} {definition}")
            conn.executescript(_SCHEMA)
            seeded = conn.execute(
                "SELECT value FROM meta WHERE key = 'seeded'"
            ).fetchone()
            if seeded is None:
                self._seed(conn)
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('seeded', ?)", (_now(),)
                )
            version_row = conn.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchone()
            if version_row is None or int(version_row["value"]) < 2:
                self._migrate_v2(conn)
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('schema_version', '2') "
                    "ON CONFLICT(key) DO UPDATE SET value = '2'"
                )
            if version_row is None or int(version_row["value"]) < 3:
                self._migrate_v3(conn)
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('schema_version', '3') "
                    "ON CONFLICT(key) DO UPDATE SET value = '3'"
                )
            if version_row is None or int(version_row["value"]) < 4:
                # v3 seeded acero matrices in kg against the per-tonne insumo.
                conn.execute(
                    "UPDATE apu_components SET quantity = quantity / 1000.0 "
                    "WHERE concept_code LIKE 'ACE-%' AND resource_code = 'MAT-ACERO' "
                    "AND quantity > 0.5"
                )
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('schema_version', '4') "
                    "ON CONFLICT(key) DO UPDATE SET value = '4'"
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

    def _migrate_v2(self, conn: sqlite3.Connection) -> None:
        """Concepts become data and the reference basket widens.

        Idempotent and edit-preserving: everything inserts OR IGNOREs, and
        user-set rendimientos in concept_settings migrate into the concepts
        table the first time.
        """
        rendimientos = {
            row["concept_code"]: row["production_rate_per_day"]
            for row in conn.execute(
                "SELECT concept_code, production_rate_per_day FROM concept_settings"
            ).fetchall()
            if row["production_rate_per_day"] is not None
        }
        for index, concept in enumerate(build_default_catalog(CostingAssumptions())):
            conn.execute(
                "INSERT OR IGNORE INTO concepts (code, description, unit, phase, "
                "production_rate_per_day, rule_key, sequence_order) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    concept.code,
                    concept.description,
                    concept.unit,
                    concept.phase,
                    rendimientos.get(concept.code, concept.production_rate_per_day),
                    concept.code,
                    index * 10,
                ),
            )
        for code, description, unit, unit_cost, resource_type in EXTRA_RESOURCES:
            conn.execute(
                "INSERT OR IGNORE INTO insumos (code, description, unit, resource_type, "
                "unit_cost, is_labor_percentage, source, source_type, region, vigencia, "
                "updated_at) VALUES (?, ?, ?, ?, ?, 0, ?, 'referencia', 'MX-CMX', ?, ?)",
                (code, description, unit, resource_type, unit_cost, SEED_SOURCE,
                 SEED_VIGENCIA, _now()),
            )
        for code, description, unit, phase, rate, order, components in EXTRA_CONCEPTS:
            conn.execute(
                "INSERT OR IGNORE INTO concepts (code, description, unit, phase, "
                "production_rate_per_day, rule_key, sequence_order) "
                "VALUES (?, ?, ?, ?, ?, NULL, ?)",
                (code, description, unit, phase, rate, 100 + order),
            )
            for resource_code, quantity in components:
                conn.execute(
                    "INSERT OR IGNORE INTO apu_components "
                    "(concept_code, resource_code, quantity) VALUES (?, ?, ?)",
                    (code, resource_code, quantity),
                )
        conn.execute(
            "UPDATE insumos SET vigencia = ? WHERE vigencia = '' AND source = ?",
            (SEED_VIGENCIA, SEED_SOURCE),
        )
        log_stage(logger, "catalog_migrated_v2", db_path=str(self.db_path))

    def _migrate_v3(self, conn: sqlite3.Connection) -> None:
        """Acero de refuerzo concepts with their matrices (OR IGNORE: a taller
        that already defined these codes keeps its own)."""
        for code, description, unit, unit_cost, resource_type in STEEL_RESOURCES:
            conn.execute(
                "INSERT OR IGNORE INTO insumos (code, description, unit, resource_type, "
                "unit_cost, is_labor_percentage, source, source_type, region, vigencia, "
                "updated_at) VALUES (?, ?, ?, ?, ?, 0, ?, 'referencia', 'MX-CMX', ?, ?)",
                (code, description, unit, resource_type, unit_cost, SEED_SOURCE,
                 SEED_VIGENCIA, _now()),
            )
        for code, description, unit, phase, rate, order, components in STEEL_CONCEPTS:
            conn.execute(
                "INSERT OR IGNORE INTO concepts (code, description, unit, phase, "
                "production_rate_per_day, rule_key, sequence_order) "
                "VALUES (?, ?, ?, ?, ?, NULL, ?)",
                (code, description, unit, phase, rate, 200 + order),
            )
            for resource_code, quantity in components:
                conn.execute(
                    "INSERT OR IGNORE INTO apu_components "
                    "(concept_code, resource_code, quantity) VALUES (?, ?, ?)",
                    (code, resource_code, quantity),
                )
        log_stage(logger, "catalog_migrated_v3", db_path=str(self.db_path))

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

    def load_concepts(self, include_inactive: bool = False) -> list[dict]:
        """Concepts ordered for the catalog: phase groups keep built-in order
        first, then manual concepts by their sequence."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM concepts"
                + ("" if include_inactive else " WHERE active = 1")
                + " ORDER BY sequence_order, code"
            ).fetchall()
        return [dict(row) for row in rows]

    def create_concept(
        self,
        *,
        code: str,
        description: str,
        unit: str,
        phase: str,
        production_rate_per_day: float,
        components: list[tuple[str, float]],
    ) -> dict:
        """A manual concept needs its APU from birth: a concept without a
        matrix cannot be priced, and unpriced never means zero."""
        if production_rate_per_day <= 0:
            raise ValueError("El rendimiento debe ser positivo.")
        if not components:
            raise ValueError("Un concepto necesita al menos un recurso en su APU.")
        book = self.load_price_book()
        for resource_code, quantity in components:
            if resource_code not in book:
                raise ValueError(f"Unknown resource {resource_code}.")
            if quantity <= 0:
                raise ValueError(f"Quantity for {resource_code} must be positive.")
        with _LOCK, self._connect() as conn:
            existing = conn.execute(
                "SELECT 1 FROM concepts WHERE code = ?", (code,)
            ).fetchone()
            if existing is not None:
                raise ValueError(f"El concepto {code} ya existe.")
            conn.execute(
                "INSERT INTO concepts (code, description, unit, phase, "
                "production_rate_per_day, rule_key) VALUES (?, ?, ?, ?, ?, NULL)",
                (code, description, unit, phase, production_rate_per_day),
            )
            for resource_code, quantity in components:
                conn.execute(
                    "INSERT INTO apu_components (concept_code, resource_code, quantity) "
                    "VALUES (?, ?, ?)",
                    (code, resource_code, quantity),
                )
            row = conn.execute("SELECT * FROM concepts WHERE code = ?", (code,)).fetchone()
        return dict(row)

    def update_concept(
        self,
        code: str,
        *,
        description: str | None = None,
        unit: str | None = None,
        phase: str | None = None,
        production_rate_per_day: float | None = None,
        active: bool | None = None,
    ) -> dict:
        if production_rate_per_day is not None and production_rate_per_day <= 0:
            raise ValueError("El rendimiento debe ser positivo.")
        with _LOCK, self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM concepts WHERE code = ?", (code,)
            ).fetchone()
            if existing is None:
                raise ValueError(f"El concepto {code} no existe.")
            conn.execute(
                "UPDATE concepts SET description = ?, unit = ?, phase = ?, "
                "production_rate_per_day = ?, active = ? WHERE code = ?",
                (
                    description if description is not None else existing["description"],
                    unit if unit is not None else existing["unit"],
                    phase if phase is not None else existing["phase"],
                    production_rate_per_day
                    if production_rate_per_day is not None
                    else existing["production_rate_per_day"],
                    int(active) if active is not None else existing["active"],
                    code,
                ),
            )
            row = conn.execute("SELECT * FROM concepts WHERE code = ?", (code,)).fetchone()
        return dict(row)

    def load_rendimientos(self) -> dict[str, float]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT code, production_rate_per_day FROM concepts"
            ).fetchall()
        return {row["code"]: row["production_rate_per_day"] for row in rows}

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
        source_type: str | None = None,
        region: str | None = None,
        vigencia: str | None = None,
    ) -> dict:
        """Update an existing insumo, or create one when all fields are given."""
        if source_type is not None and source_type not in (
            "referencia", "cotizacion", "publicacion", "calculado",
        ):
            raise ValueError("Tipo de fuente inválido.")
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
                    "unit_cost, is_labor_percentage, source, source_type, region, "
                    "vigencia, updated_at) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)",
                    (
                        code, description, unit, resource_type, unit_cost,
                        source or "", source_type or "cotizacion",
                        region or "MX-CMX", vigencia or "", _now(),
                    ),
                )
            else:
                conn.execute(
                    "UPDATE insumos SET description = ?, unit = ?, resource_type = ?, "
                    "unit_cost = ?, source = ?, source_type = ?, region = ?, "
                    "vigencia = ?, updated_at = ? WHERE code = ?",
                    (
                        description if description is not None else existing["description"],
                        unit if unit is not None else existing["unit"],
                        resource_type
                        if resource_type is not None
                        else existing["resource_type"],
                        unit_cost if unit_cost is not None else existing["unit_cost"],
                        source if source is not None else existing["source"],
                        source_type
                        if source_type is not None
                        else existing["source_type"],
                        region if region is not None else existing["region"],
                        vigencia if vigencia is not None else existing["vigencia"],
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
                "UPDATE concepts SET production_rate_per_day = ? WHERE code = ?",
                (production_rate_per_day, concept_code),
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
                    "UPDATE insumos SET unit_cost = ?, source = ?, "
                    "source_type = 'cotizacion', updated_at = ? WHERE code = ?",
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


    # ------------------------------------------------- reference library

    def list_sources(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM price_sources ORDER BY vigencia DESC, name"
            ).fetchall()
        return [dict(row) for row in rows]

    def import_reference(
        self, source: dict, rows: Iterable[dict], *, sha256: str | None = None
    ) -> int:
        """Replace a source's rows with a fresh parse. Zero prices are not
        prices ("por cotización") and are left out."""
        kept = [
            r for r in rows
            if r.get("price") and float(r["price"]) > 0 and r.get("clave") and r.get("unit")
        ]
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO price_sources (source_key, name, publisher, region, vigencia, "
                "kind, url, sha256, imported_at, row_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(source_key) DO UPDATE SET name = excluded.name, "
                "publisher = excluded.publisher, region = excluded.region, "
                "vigencia = excluded.vigencia, kind = excluded.kind, url = excluded.url, "
                "sha256 = excluded.sha256, imported_at = excluded.imported_at, "
                "row_count = excluded.row_count",
                (
                    source["key"], source["name"], source.get("publisher", ""),
                    source.get("region", "MX"), source.get("vigencia", ""),
                    source.get("kind", "precios_unitarios"), source.get("url", ""),
                    sha256, _now(), len(kept),
                ),
            )
            conn.execute("DELETE FROM reference_prices WHERE source_key = ?", (source["key"],))
            conn.executemany(
                "INSERT INTO reference_prices (source_key, clave, description, unit, price, "
                "group_clave, group_description, extra, page) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        source["key"], str(r["clave"]), str(r["description"])[:600],
                        str(r["unit"]), float(r["price"]), str(r.get("group_clave") or ""),
                        str(r.get("group_description") or "")[:600],
                        json.dumps(r.get("extra"), ensure_ascii=False) if r.get("extra") else None,
                        r.get("page"),
                    )
                    for r in kept
                ],
            )
        log_stage(logger, "reference_imported", source=source["key"], rows=len(kept))
        return len(kept)

    def search_reference(
        self, query: str, *, source_key: str | None = None, limit: int = 50
    ) -> list[dict]:
        tokens = [t for t in query.lower().split() if t][:6]
        where = ["1 = 1"]
        params: list[object] = []
        if source_key:
            where.append("r.source_key = ?")
            params.append(source_key)
        for token in tokens:
            where.append("(lower(r.description) LIKE ? OR lower(r.clave) LIKE ? "
                         "OR lower(r.group_description) LIKE ?)")
            like = f"%{token}%"
            params.extend([like, like, like])
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT r.*, s.name AS source_name, s.vigencia AS source_vigencia, "
                "s.region AS source_region FROM reference_prices r "
                "JOIN price_sources s ON s.source_key = r.source_key "
                f"WHERE {' AND '.join(where)} ORDER BY r.clave LIMIT ?",
                (*params, max(1, min(limit, 200))),
            ).fetchall()
        return [self._reference_row(row) for row in rows]

    @staticmethod
    def _reference_row(row: sqlite3.Row) -> dict:
        record = dict(row)
        extra = record.get("extra")
        record["extra"] = json.loads(extra) if extra else None
        return record

    def get_reference(self, ref_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT r.*, s.name AS source_name, s.vigencia AS source_vigencia, "
                "s.region AS source_region FROM reference_prices r "
                "JOIN price_sources s ON s.source_key = r.source_key WHERE r.ref_id = ?",
                (ref_id,),
            ).fetchone()
        return self._reference_row(row) if row else None

    def adopt_reference(self, insumo_code: str, ref_id: int) -> dict:
        """Price an insumo from a published row, carrying the publication,
        clave, region and vigencia as provenance."""
        reference = self.get_reference(ref_id)
        if reference is None:
            raise ValueError("la referencia no existe")
        return self.upsert_insumo(
            insumo_code,
            unit_cost=float(reference["price"]),
            source=f"{reference['source_name']} · {reference['clave']}",
            source_type="publicacion",
            region=reference["source_region"],
            vigencia=reference["source_vigencia"],
        )

    # ------------------------------------------------- settings + analyses

    def get_setting(self, key: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM workspace_settings WHERE key = ?", (key,)
            ).fetchone()
        return json.loads(row["value"]) if row else None

    def set_setting(self, key: str, value: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO workspace_settings (key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                "updated_at = excluded.updated_at",
                (key, json.dumps(value, ensure_ascii=False), _now()),
            )

    def get_analysis(self, code: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM insumo_analysis WHERE code = ?", (code,)).fetchone()
        if row is None:
            return None
        return {
            "code": row["code"], "kind": row["kind"], "params": json.loads(row["params"]),
            "result": json.loads(row["result"]) if row["result"] else None,
            "updated_at": row["updated_at"],
        }

    def set_analysis(self, code: str, kind: str, params: dict, result: dict | None) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO insumo_analysis (code, kind, params, result, updated_at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(code) DO UPDATE SET kind = excluded.kind, "
                "params = excluded.params, result = excluded.result, "
                "updated_at = excluded.updated_at",
                (code, kind, json.dumps(params, ensure_ascii=False),
                 json.dumps(result, ensure_ascii=False) if result is not None else None, _now()),
            )

    def list_analyses(self, kind: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT code FROM insumo_analysis WHERE kind = ? ORDER BY code", (kind,)
            ).fetchall()
        return [a for a in (self.get_analysis(row["code"]) for row in rows) if a]


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
