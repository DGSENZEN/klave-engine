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
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from klave_engine.common.logging import get_logger, log_stage
from klave_engine.costing.catalog import build_default_catalog
from klave_engine.costing.instalaciones import (
    CODIGOS_CON_REGLA as INSTALACIONES_CON_REGLA,
)
from klave_engine.costing.instalaciones import (
    CONCEPTOS_STORE as INSTALACIONES_CONCEPTS,
)
from klave_engine.costing.insumos import APU_TEMPLATES, RESOURCES
from klave_engine.costing.matching import unit_key
from klave_engine.costing.models import CostingAssumptions, Resource, ResourceType

logger = get_logger(__name__)

CATALOG_DB_FILENAME = "catalog.db"
SEED_SOURCE = "Referencia Klave"

_LOCK = threading.Lock()


class UnitMismatch(ValueError):
    """A price in one unit offered for something measured in another."""

    def __init__(self, code: str, own_unit: str, other_unit: str) -> None:
        self.code, self.own_unit, self.other_unit = code, own_unit, other_unit
        super().__init__(
            f"{code} se mide en {own_unit} y la referencia está en {other_unit}; "
            "un precio por unidad distinta multiplica mal. Elige una referencia en "
            f"{own_unit} o fuerza la adopción explicando por qué."
        )


def _check_units(code: str, own_unit: str, other_unit: str, force: bool) -> None:
    if force or unit_key(own_unit) == unit_key(other_unit):
        return
    raise UnitMismatch(code, own_unit, other_unit)

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
CREATE TABLE IF NOT EXISTS concept_aliases (
    concept_code TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    ref_id INTEGER,
    target_code TEXT,
    clave TEXT NOT NULL,
    description TEXT NOT NULL,
    unit TEXT NOT NULL DEFAULT '',
    price REAL,
    source TEXT NOT NULL DEFAULT '',
    vigencia TEXT NOT NULL DEFAULT '',
    actor TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    project_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS plantillas (
    key TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    tipologia TEXT NOT NULL DEFAULT '',
    area_m2 REAL NOT NULL,
    source_key TEXT NOT NULL DEFAULT '',
    rows INTEGER NOT NULL DEFAULT 0,
    actor TEXT NOT NULL DEFAULT '',
    phase_shares TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS parametric_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    concept_code TEXT NOT NULL,
    basis TEXT NOT NULL DEFAULT 'm2_construida',
    factor REAL NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    plantilla_key TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    engine_read INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE(concept_code, basis, plantilla_key)
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
CREATE TABLE IF NOT EXISTS inventory_mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    pattern TEXT NOT NULL,
    concept_code TEXT NOT NULL,
    factor REAL NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE(kind, pattern)
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
SLAB_CONCEPT_CODES = ("EST-012", "EST-013", "CIM-007")
BEAM_CONCEPT_CODES_V7 = ("CIM-008",)
FAMILY_CONCEPT_CODES_V9 = ("EST-014", "CIM-010")
SLAB_STEEL_CONCEPTS: list[tuple[str, str, str, str, float, int, list[tuple[str, float]]]] = [
    ("ACE-006", "Acero de refuerzo fy=4200 kg/cm² en losas macizas y de cimentación (parrillas), "
     "habilitado y armado", "KG", "Estructura", 200.0, 45,
     [("MAT-ACERO", 0.00104), ("MAT-ALAMBRE", 0.02), ("MO-FIERRERO", 0.0060),
      ("MO-AYUD", 0.0060), ("EQ-HERRAMIENTA", 1.0)]),
]
FORMWORK_CONCEPTS_V7: list[tuple[str, str, str, str, float, int, list[tuple[str, float]]]] = [
    (
        "CIM-009", "Cimbra común en contratrabes, acabado no aparente", "M2",
        "Cimentación", 12.0, 33,
        [("MAT-CIMBRA", 0.25), ("MO-CUAD-CARP", 0.085), ("EQ-HERRAMIENTA", 1.0)],
    ),
]
TERRACERIAS_CONCEPT_CODES = ("TER-001", "TER-002", "TER-003")
TERRACERIAS_RESOURCES: list[tuple[str, str, str, float, str]] = [
    ("EQ-MOTOCONFORMADORA", "Motoconformadora 140 HP, costo horario (referencia SICT)", "HORA",
     0.0, "equipo"),
    ("EQ-VIBROCOMPACTADOR", "Vibrocompactador liso 10 t, costo horario (referencia SICT)",
     "HORA", 0.0, "equipo"),
    ("EQ-PIPA", "Pipa de agua 10 000 L, costo horario (referencia)", "HORA", 0.0, "equipo"),
]
ACABADOS_CONCEPT_CODES = ("ACA-001", "ACA-002", "ACA-003", "ACA-004", "PIS-001", "PIS-002")
# v14: pilotes in metres (CIM-011) with the drilling rig, and the plantilla
# concept (CIM-003) in the built-in catalog.
PILES_CONCEPT_CODES = ("CIM-011", "CIM-003", "CIM-010")
PILES_RESOURCES: list[tuple[str, str, str, float, str]] = [
    ("EQ-PERFORADORA", "Perforadora rotatoria para pilotes Ø60–120 cm, costo horario "
     "(referencia SICT)", "HORA", 0.0, "equipo"),
]
ACABADOS_RESOURCES: list[tuple[str, str, str, float, str]] = [
    ("MAT-PINTURA", "Pintura vinílica acrílica, cubeta 19 L (referencia)", "L", 0.0,
     "material"),
    ("MAT-SELLADOR", "Sellador vinílico 5×1 (referencia)", "L", 0.0, "material"),
    ("MAT-PISO-CER", "Loseta cerámica 60×60 cm tráfico residencial (referencia)", "M2",
     0.0, "material"),
    ("MAT-ADHESIVO", "Adhesivo para loseta base cemento, saco 20 kg (referencia)", "KG",
     0.0, "material"),
    ("MAT-YESO", "Yeso para construcción, saco 40 kg (referencia)", "KG", 0.0, "material"),
    ("MO-PINTOR", "Pintor (cuadrilla pintor + ayudante, salario real)", "JOR", 0.0,
     "mano_de_obra"),
    ("MO-YESERO", "Yesero (cuadrilla yesero + ayudante, salario real)", "JOR", 0.0,
     "mano_de_obra"),
]
SLAB_RESOURCES: list[tuple[str, str, str, float, str]] = [
    ("MAT-VIGUETA", "Vigueta pretensada de 13 cm (referencia)", "M", 0.0, "material"),
    ("MAT-BOVEDILLA", "Bovedilla de cemento-arena 15×25×56 cm (referencia)", "PZA", 0.0,
     "material"),
]

EXTRA_RESOURCES: list[tuple[str, str, str, float, str]] = [
    ("MAT-CEM", "Cemento gris CPC 30R", "TON", 0.0, "material"),
    ("MAT-ARENA", "Arena de mina", "M3", 0.0, "material"),
    ("MAT-GRAVA", "Grava triturada 3/4\"", "M3", 0.0, "material"),
    ("MAT-AGUA", "Agua para obra", "M3", 0.0, "material"),
    ("MAT-CONC150", "Concreto hecho en obra f'c=150 kg/cm²", "M3", 0.0, "material"),
    ("MAT-MALLA", "Malla electrosoldada 6x6-10/10", "M2", 0.0, "material"),
    ("MAT-ALAMBRE", "Alambre recocido", "KG", 0.0, "material"),
    ("MAT-CLAVO", "Clavo para cimbra", "KG", 0.0, "material"),
    ("MAT-MADERA", "Madera de pino 3a para obra", "PT", 0.0, "material"),
    ("MAT-TEPETATE", "Tepetate para relleno", "M3", 0.0, "material"),
    ("MO-OF-ALB", "Oficial albañil", "JOR", 0.0, "mano_de_obra"),
    ("MO-AYUD", "Ayudante general", "JOR", 0.0, "mano_de_obra"),
    ("EQ-BAILARINA", "Compactador tipo bailarina", "JOR", 0.0, "equipo"),
    ("EQ-CAMION", "Camión de volteo 7 m³ (viaje)", "VJE", 0.0, "equipo"),
]

# Manual concepts: priced through their APU, quantified only by documented
# adjustments or viewer measurements — the estimator's own takeoff.
# Acero de refuerzo: resources and concepts the steel stage prices. Labor
# here is a reference rate (replace it by applying salario real).
STEEL_RESOURCES: list[tuple[str, str, str, float, str]] = [
    ("MAT-ALAMBRE", "Alambre recocido cal. 18", "KG", 0.0, "material"),
    ("MAT-MALLA66", "Malla electrosoldada 6x6-10/10", "M2", 0.0, "material"),
    ("MO-FIERRERO", "Fierrero (oficial)", "JOR", 0.0, "mano_de_obra"),
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

# Cimbra: contact formwork priced per m² with reuse (4 usos ≈ 0.25 m² of
# material per m² of contact) and a carpentry crew rendimiento.
FORMWORK_CONCEPTS: list[tuple[str, str, str, str, float, int, list[tuple[str, float]]]] = [
    (
        "CIM-006", "Cimbra común en zapatas y dados, acabado no aparente", "M2",
        "Cimentación", 14.0, 32,
        [("MAT-CIMBRA", 0.25), ("MO-CUAD-CARP", 0.070), ("EQ-HERRAMIENTA", 1.0)],
    ),
    (
        "EST-008", "Cimbra común en castillos y columnas, acabado no aparente", "M2",
        "Estructura", 12.0, 44,
        [("MAT-CIMBRA", 0.25), ("MO-CUAD-CARP", 0.085), ("EQ-HERRAMIENTA", 1.0)],
    ),
    (
        "EST-009", "Cimbra común en trabes, acabado no aparente, incluye obra falsa", "M2",
        "Estructura", 10.0, 45,
        [("MAT-CIMBRA", 0.30), ("MO-CUAD-CARP", 0.100), ("EQ-HERRAMIENTA", 1.0)],
    ),
    (
        "EST-010", "Cimbra común en dalas y cerramientos", "M2",
        "Estructura", 14.0, 46,
        [("MAT-CIMBRA", 0.25), ("MO-CUAD-CARP", 0.070), ("EQ-HERRAMIENTA", 1.0)],
    ),
    (
        "EST-011", "Cimbra de contacto en losa maciza, incluye obra falsa", "M2",
        "Estructura", 12.0, 47,
        [("MAT-CIMBRA", 0.30), ("MO-CUAD-CARP", 0.085), ("EQ-HERRAMIENTA", 1.0)],
    ),
]

# Resources that the derived lines (ACE-*, cimbra, CIM-003) already price.
DOUBLE_COUNTED_RESOURCES = ("MAT-ACERO", "MAT-CIMBRA", "MAT-PLANTILLA")

# The concrete matrices as v12 seeded them, with acero/cimbra/plantilla inside.
CONCRETE_MATRICES_V12: dict[str, list[tuple[str, float]]] = {
    "CIM-002": [
        ("MAT-CONC250", 1.05), ("MAT-ACERO", 0.075), ("MAT-CIMBRA", 1.20),
        ("MAT-PLANTILLA", 0.080), ("MO-CUAD-ALB", 0.45), ("MO-CUAD-FIE", 0.35),
        ("EQ-VIBRADOR", 0.12), ("EQ-REVOLVEDORA", 0.08), ("EQ-HERRAMIENTA", 1.0),
    ],
    "EST-001": [
        ("MAT-CONC250", 1.05), ("MAT-ACERO", 0.160), ("MAT-CIMBRA", 9.00),
        ("MO-CUAD-ALB", 0.90), ("MO-CUAD-FIE", 0.70), ("MO-CUAD-CARP", 0.80),
        ("EQ-VIBRADOR", 0.25), ("EQ-HERRAMIENTA", 1.0),
    ],
    "EST-005": [
        ("MAT-CONC250", 0.033), ("MAT-ACERO", 0.0045), ("MAT-CIMBRA", 0.42),
        ("MO-CUAD-ALB", 0.035), ("MO-CUAD-FIE", 0.020), ("MO-CUAD-CARP", 0.030),
        ("EQ-HERRAMIENTA", 1.0),
    ],
    "CIM-008": [
        ("MAT-CONC250", 1.05), ("MAT-ACERO", 0.120), ("MAT-CIMBRA", 5.00),
        ("MO-CUAD-ALB", 0.70), ("MO-CUAD-FIE", 0.55), ("MO-CUAD-CARP", 0.50),
        ("EQ-VIBRADOR", 0.20), ("EQ-HERRAMIENTA", 1.0),
    ],
    "EST-002": [
        ("MAT-CONC250", 1.05), ("MAT-ACERO", 0.140), ("MAT-CIMBRA", 6.50),
        ("MO-CUAD-ALB", 0.75), ("MO-CUAD-FIE", 0.60), ("MO-CUAD-CARP", 0.65),
        ("EQ-VIBRADOR", 0.20), ("EQ-HERRAMIENTA", 1.0),
    ],
    "EST-003": [
        ("MAT-CONC250", 0.110), ("MAT-ACERO", 0.0085), ("MAT-CIMBRA", 1.05),
        ("MO-CUAD-ALB", 0.120), ("MO-CUAD-CARP", 0.100), ("EQ-VIBRADOR", 0.020),
        ("EQ-HERRAMIENTA", 1.0),
    ],
}

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
        # The taller this store belongs to; None for the legacy shared file.
        self.workspace_id: str | None = None
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
            if version_row is None or int(version_row["value"]) < 5:
                self._seed_concepts(conn, FORMWORK_CONCEPTS, 300)
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('schema_version', '5') "
                    "ON CONFLICT(key) DO UPDATE SET value = '5'"
                )
            if version_row is None or int(version_row["value"]) < 6:
                self._migrate_v6(conn)
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('schema_version', '6') "
                    "ON CONFLICT(key) DO UPDATE SET value = '6'"
                )
            if version_row is None or int(version_row["value"]) < 7:
                self._sync_builtin_concepts(conn, BEAM_CONCEPT_CODES_V7)
                self._seed_concepts(conn, FORMWORK_CONCEPTS_V7, 300)
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('schema_version', '7') "
                    "ON CONFLICT(key) DO UPDATE SET value = '7'"
                )
            if version_row is None or int(version_row["value"]) < 8:
                self._migrate_v8(conn)
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('schema_version', '8') "
                    "ON CONFLICT(key) DO UPDATE SET value = '8'"
                )
            if version_row is None or int(version_row["value"]) < 9:
                self._sync_builtin_concepts(conn, FAMILY_CONCEPT_CODES_V9)
                # EST-005 (dalas) was a manual concept; it now binds to the
                # dala/cerramiento rule and keeps the taller's description and matrix.
                conn.execute(
                    "UPDATE concepts SET rule_key = 'EST-005' WHERE code = 'EST-005' "
                    "AND rule_key IS NULL"
                )
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('schema_version', '9') "
                    "ON CONFLICT(key) DO UPDATE SET value = '9'"
                )
            if version_row is None or int(version_row["value"]) < 10:
                self._seed_concepts(conn, SLAB_STEEL_CONCEPTS, 200)
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('schema_version', '10') "
                    "ON CONFLICT(key) DO UPDATE SET value = '10'"
                )
            if version_row is None or int(version_row["value"]) < 11:
                self._migrate_v11(conn)
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('schema_version', '11') "
                    "ON CONFLICT(key) DO UPDATE SET value = '11'"
                )
            if version_row is None or int(version_row["value"]) < 12:
                self._seed_resources(conn, TERRACERIAS_RESOURCES)
                self._sync_builtin_concepts(conn, TERRACERIAS_CONCEPT_CODES)
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('schema_version', '12') "
                    "ON CONFLICT(key) DO UPDATE SET value = '12'"
                )
            if version_row is None or int(version_row["value"]) < 13:
                self._migrate_v13(conn)
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('schema_version', '13') "
                    "ON CONFLICT(key) DO UPDATE SET value = '13'"
                )
            if version_row is None or int(version_row["value"]) < 14:
                self._seed_resources(conn, PILES_RESOURCES)
                self._sync_builtin_concepts(conn, PILES_CONCEPT_CODES)
                conn.execute(
                    "UPDATE concepts SET description = ? WHERE code = 'CIM-010' "
                    "AND description = ?",
                    (
                        "Pilote de concreto colado en sitio (pieza, longitud según proyecto)",
                        "Pilote de concreto colado en sitio (longitud según proyecto)",
                    ),
                )
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('schema_version', '14') "
                    "ON CONFLICT(key) DO UPDATE SET value = '14'"
                )
            if version_row is None or int(version_row["value"]) < 15:
                self._sync_builtin_concepts(conn, ("EST-015",))
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('schema_version', '15') "
                    "ON CONFLICT(key) DO UPDATE SET value = '15'"
                )
            if version_row is None or int(version_row["value"]) < 16:
                # Instalaciones: conceptos sin matriz, para que el
                # levantamiento de hidráulica, sanitaria, gas, aire y
                # eléctrica tenga a dónde llegar. El precio lo pone el taller.
                self._seed_concepts(conn, INSTALACIONES_CONCEPTS, 400)
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('schema_version', '16') "
                    "ON CONFLICT(key) DO UPDATE SET value = '16'"
                )
            if version_row is None or int(version_row["value"]) < 17:
                # Los conceptos de instalaciones dejaron de ser manuales: los
                # detectores de muebles y corridas los cuantifican solos.
                # Sólo se atan los que el motor sabe leer; el resto sigue
                # llenándose por asignación del levantamiento.
                self._sync_builtin_concepts(conn, INSTALACIONES_CON_REGLA)
                for code in INSTALACIONES_CON_REGLA:
                    conn.execute(
                        "UPDATE concepts SET rule_key = ? WHERE code = ? AND rule_key IS NULL",
                        (code, code),
                    )
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('schema_version', '17') "
                    "ON CONFLICT(key) DO UPDATE SET value = '17'"
                )
            if version_row is None or int(version_row["value"]) < 18:
                # Cancelería y carpintería: los vanos que el detector lee del
                # plano dejan de salir del presupuesto en blanco.
                self._seed_concepts(conn, INSTALACIONES_CONCEPTS, 400)
                self._sync_builtin_concepts(conn, INSTALACIONES_CON_REGLA)
                for code in INSTALACIONES_CON_REGLA:
                    conn.execute(
                        "UPDATE concepts SET rule_key = ? WHERE code = ? AND rule_key IS NULL",
                        (code, code),
                    )
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('schema_version', '18') "
                    "ON CONFLICT(key) DO UPDATE SET value = '18'"
                )
            if version_row is None or int(version_row["value"]) < 19:
                # Muebles, piezas de red que se cuentan por pieza, e
                # impermeabilización: nueve familias que el motor ya detectaba
                # y ningún concepto recibía, más el mueble aparte de su salida.
                self._seed_concepts(conn, INSTALACIONES_CONCEPTS, 400)
                self._sync_builtin_concepts(conn, INSTALACIONES_CON_REGLA)
                for code in INSTALACIONES_CON_REGLA:
                    conn.execute(
                        "UPDATE concepts SET rule_key = ? WHERE code = ? AND rule_key IS NULL",
                        (code, code),
                    )
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('schema_version', '19') "
                    "ON CONFLICT(key) DO UPDATE SET value = '19'"
                )
            if version_row is None or int(version_row["value"]) < 20:
                # De qué importación salió cada concepto, para poder deshacerla.
                columnas = {
                    row["name"] for row in conn.execute("PRAGMA table_info(concepts)")
                }
                if "import_source" not in columnas:
                    conn.execute(
                        "ALTER TABLE concepts ADD COLUMN import_source TEXT NOT NULL DEFAULT ''"
                    )
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('schema_version', '20') "
                    "ON CONFLICT(key) DO UPDATE SET value = '20'"
                )
            if version_row is None or int(version_row["value"]) < 21:
                # Los precios que sembró Klave los había escrito yo: no salían
                # de ninguna publicación ni los había cotizado nadie. Se van
                # también de los catálogos que ya existían, no sólo de la
                # semilla — dejarlos ahí sería quitarlos de boquilla.
                #
                # El insumo se queda con lo que sí es un hecho —su clave, su
                # descripción, su unidad— y sin precio, que es distinto de
                # valer cero. El que el taller ya haya cotizado o importado
                # no se toca: ése tiene dueño.
                conn.execute(
                    "UPDATE insumos SET unit_cost = 0, source = '', source_type = '', "
                    "vigencia = '' WHERE source = ? AND is_labor_percentage = 0",
                    (SEED_SOURCE,),
                )
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('schema_version', '21') "
                    "ON CONFLICT(key) DO UPDATE SET value = '21'"
                )
            if version_row is None or int(version_row["value"]) < 22:
                # La losa sin sistema declarado deja de cobrarse como
                # reticular: EST-016 la recibe, sin matriz — sin precio hasta
                # que el plano declare el sistema o el taller la mapee.
                self._sync_builtin_concepts(conn, ("EST-016",))
                conn.execute(
                    "UPDATE concepts SET rule_key = ? WHERE code = ? AND rule_key IS NULL",
                    ("EST-016", "EST-016"),
                )
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('schema_version', '22') "
                    "ON CONFLICT(key) DO UPDATE SET value = '22'"
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

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """One connection per operation: commit on success, roll back on
        error, and always close (the bare ``with sqlite3.connect()`` pattern
        commits but leaks the file handle). WAL lets readers proceed while a
        write is in flight."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            with conn:
                yield conn
        finally:
            conn.close()

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
                    concept.code if concept.rule is not None else None,
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

    def _migrate_v6(self, conn: sqlite3.Connection) -> None:
        """Slab systems become their own concepts (vigueta y bovedilla, losa
        maciza, losa de cimentación) with reference matrices. OR IGNORE: a
        taller that already defined these codes keeps its own."""
        for code, description, unit, unit_cost, resource_type in SLAB_RESOURCES:
            conn.execute(
                "INSERT OR IGNORE INTO insumos (code, description, unit, resource_type, "
                "unit_cost, is_labor_percentage, source, source_type, region, vigencia, "
                "updated_at) VALUES (?, ?, ?, ?, ?, 0, ?, 'referencia', 'MX-CMX', ?, ?)",
                (code, description, unit, resource_type, unit_cost, SEED_SOURCE,
                 SEED_VIGENCIA, _now()),
            )
        self._sync_builtin_concepts(conn, SLAB_CONCEPT_CODES)
        log_stage(logger, "catalog_migrated_v6", db_path=str(self.db_path))

    @staticmethod
    def _seed_resources(
        conn: sqlite3.Connection, resources: list[tuple[str, str, str, float, str]]
    ) -> None:
        """Reference insumos, OR IGNORE: a taller's own rows always win."""
        for code, description, unit, unit_cost, resource_type in resources:
            conn.execute(
                "INSERT OR IGNORE INTO insumos (code, description, unit, resource_type, "
                "unit_cost, is_labor_percentage, source, source_type, region, vigencia, "
                "updated_at) VALUES (?, ?, ?, ?, ?, 0, ?, 'referencia', 'MX-CMX', ?, ?)",
                (code, description, unit, resource_type, unit_cost, SEED_SOURCE,
                 SEED_VIGENCIA, _now()),
            )

    def _migrate_v13(self, conn: sqlite3.Connection) -> None:
        """Acero, cimbra y plantilla were priced twice: inside the concrete
        matrices and again as their own derived lines (ACE-*, cimbra, CIM-003).
        A matrix that still equals the v12 seed is replaced by the concrete-only
        one; a matrix the taller edited is left alone and reported."""
        kept: list[str] = []
        for code, old_components in CONCRETE_MATRICES_V12.items():
            rows = conn.execute(
                "SELECT resource_code, quantity FROM apu_components WHERE concept_code = ?",
                (code,),
            ).fetchall()
            current = {row["resource_code"]: round(float(row["quantity"]), 6) for row in rows}
            if not current:
                continue
            if current != {r: round(q, 6) for r, q in old_components}:
                if any(r in DOUBLE_COUNTED_RESOURCES for r in current):
                    kept.append(code)
                continue
            conn.execute("DELETE FROM apu_components WHERE concept_code = ?", (code,))
            for resource_code, quantity in APU_TEMPLATES[code]:
                conn.execute(
                    "INSERT INTO apu_components (concept_code, resource_code, quantity) "
                    "VALUES (?, ?, ?)",
                    (code, resource_code, quantity),
                )
        conn.execute(
            "UPDATE concepts SET description = ? WHERE code = 'CIM-002' AND description = ?",
            (
                "Concreto f'c=250 kg/cm² en zapatas y dados",
                "Concreto f'c=250 kg/cm² en zapatas y dados, incluye acero, cimbra y plantilla",
            ),
        )
        log_stage(
            logger, "catalog_migrated_v13", db_path=str(self.db_path),
            kept_with_steel_or_cimbra=",".join(kept),
        )

    def _migrate_v11(self, conn: sqlite3.Connection) -> None:
        """Albañilería y acabados read from the architecture (aplanado,
        pintura, plafón, piso, firme) with reference matrices. OR IGNORE: a
        taller that already defined these codes keeps its own."""
        for code, description, unit, unit_cost, resource_type in ACABADOS_RESOURCES:
            conn.execute(
                "INSERT OR IGNORE INTO insumos (code, description, unit, resource_type, "
                "unit_cost, is_labor_percentage, source, source_type, region, vigencia, "
                "updated_at) VALUES (?, ?, ?, ?, ?, 0, ?, 'referencia', 'MX-CMX', ?, ?)",
                (code, description, unit, resource_type, unit_cost, SEED_SOURCE,
                 SEED_VIGENCIA, _now()),
            )
        self._sync_builtin_concepts(conn, ACABADOS_CONCEPT_CODES)
        log_stage(logger, "catalog_migrated_v11", db_path=str(self.db_path))

    @staticmethod
    def _migrate_v8(conn: sqlite3.Connection) -> None:
        """A concept may take its precio unitario from a reference row (the
        taller's catálogo or a publication) instead of its matrix; the row's
        source, clave and vigencia travel with it."""
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(concepts)").fetchall()}
        for column, kind in (
            ("price_override", "REAL"), ("price_source_key", "TEXT"), ("price_source", "TEXT"),
            ("price_clave", "TEXT"), ("price_vigencia", "TEXT"),
        ):
            if column not in existing:
                conn.execute(f"ALTER TABLE concepts ADD COLUMN {column} {kind}")

    def check_concept_reference(self, code: str, ref_id: int) -> str:
        """Por qué esta adopción no procedería, o "" si procede.

        Existe para que quien vaya a aplicar varias adopciones pueda
        comprobarlas todas antes de tocar la primera: dejar un presupuesto a
        medio arreglar es peor que no haberlo tocado."""
        reference = self.get_reference(ref_id)
        if reference is None:
            return "la referencia no existe."
        with self._connect() as conn:
            concept = conn.execute(
                "SELECT unit FROM concepts WHERE code = ?", (code,)
            ).fetchone()
        if concept is None:
            return f"el concepto {code} no existe."
        try:
            _check_units(code, str(concept["unit"]), str(reference["unit"]), False)
        except UnitMismatch as exc:
            return str(exc)
        return ""

    def adopt_concept_reference(self, code: str, ref_id: int, *, force: bool = False) -> dict:
        """Price a concept from a reference row: its P.U. replaces the matrix
        until cleared, with the row's provenance on every presupuesto. The
        row's unit must be the concept's ($/m never prices an M3) unless the
        engineer forces it knowingly."""
        reference = self.get_reference(ref_id)
        if reference is None:
            raise ValueError("la referencia no existe")
        with _LOCK, self._connect() as conn:
            concept = conn.execute(
                "SELECT unit FROM concepts WHERE code = ?", (code,)
            ).fetchone()
            if concept is None:
                raise ValueError(f"El concepto {code} no existe.")
            _check_units(code, str(concept["unit"]), str(reference["unit"]), force)
            conn.execute(
                "UPDATE concepts SET price_override = ?, price_source_key = ?, price_source = ?, "
                "price_clave = ?, price_vigencia = ? WHERE code = ?",
                (
                    float(reference["price"]), reference["source_key"], reference["source_name"],
                    reference["clave"], reference["source_vigencia"], code,
                ),
            )
            row = conn.execute("SELECT * FROM concepts WHERE code = ?", (code,)).fetchone()
        return dict(row)

    # ------------------------------------------------------ plantillas / paramétricos

    def create_priced_concept(
        self, *, code: str, description: str, unit: str, phase: str,
        production_rate_per_day: float, ref_id: int,
    ) -> dict:
        """A manual concept priced by an adopted reference row from birth (no
        matrix): how a past presupuesto's line becomes a concept the taller
        can use again."""
        with _LOCK, self._connect() as conn:
            if conn.execute("SELECT 1 FROM concepts WHERE code = ?", (code,)).fetchone():
                raise ValueError(f"El concepto {code} ya existe.")
            conn.execute(
                "INSERT INTO concepts (code, description, unit, phase, "
                "production_rate_per_day, rule_key, import_source) "
                "VALUES (?, ?, ?, ?, ?, NULL, ?)",
                (code, description, unit, phase, production_rate_per_day, "plantilla"),
            )
        return self.adopt_concept_reference(code, ref_id)

    def save_plantilla(
        self, *, key: str, name: str, tipologia: str, area_m2: float, source_key: str,
        rows: int, actor: str, phase_shares: dict | None = None,
    ) -> dict:
        with _LOCK, self._connect() as conn:
            try:
                conn.execute("ALTER TABLE plantillas ADD COLUMN phase_shares TEXT")
            except sqlite3.OperationalError:
                pass  # column already there
            conn.execute(
                "INSERT INTO plantillas (key, name, tipologia, area_m2, source_key, rows, actor, "
                "phase_shares, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET "
                "name = excluded.name, tipologia = excluded.tipologia, area_m2 = excluded.area_m2, "
                "source_key = excluded.source_key, rows = excluded.rows, actor = excluded.actor, "
                "phase_shares = excluded.phase_shares, created_at = excluded.created_at",
                (key, name, tipologia, area_m2, source_key, rows, actor,
                 json.dumps(phase_shares or {}), _now()),
            )
            conn.execute("DELETE FROM parametric_rules WHERE plantilla_key = ?", (key,))
            row = conn.execute("SELECT * FROM plantillas WHERE key = ?", (key,)).fetchone()
        return dict(row)

    def list_plantillas(self) -> list[dict]:
        with self._connect() as conn:
            try:
                rows = conn.execute(
                    "SELECT * FROM plantillas ORDER BY created_at DESC"
                ).fetchall()
            except sqlite3.OperationalError:
                return []
        out = []
        for r in rows:
            record = dict(r)
            shares = record.get("phase_shares")
            record["phase_shares"] = json.loads(shares) if shares else {}
            out.append(record)
        return out

    def delete_plantilla(self, key: str) -> bool:
        with _LOCK, self._connect() as conn:
            conn.execute("DELETE FROM parametric_rules WHERE plantilla_key = ?", (key,))
            removed = conn.execute("DELETE FROM plantillas WHERE key = ?", (key,)).rowcount
        return bool(removed)

    def add_parametric_rule(
        self, *, concept_code: str, basis: str, factor: float, source: str = "",
        plantilla_key: str = "", note: str = "", engine_read: bool = False,
    ) -> dict:
        if factor <= 0:
            raise ValueError("El factor debe ser positivo.")
        with _LOCK, self._connect() as conn:
            if conn.execute(
                "SELECT 1 FROM concepts WHERE code = ?", (concept_code,)
            ).fetchone() is None:
                raise ValueError(f"El concepto {concept_code} no existe.")
            conn.execute(
                "INSERT INTO parametric_rules (concept_code, basis, factor, source, "
                "plantilla_key, note, engine_read, active, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?) "
                "ON CONFLICT(concept_code, basis, plantilla_key) DO UPDATE SET "
                "factor = excluded.factor, source = excluded.source, note = excluded.note, "
                "engine_read = excluded.engine_read, active = 1, created_at = excluded.created_at",
                (concept_code, basis, factor, source, plantilla_key, note, int(engine_read),
                 _now()),
            )
            row = conn.execute(
                "SELECT * FROM parametric_rules WHERE concept_code = ? AND basis = ? "
                "AND plantilla_key = ?", (concept_code, basis, plantilla_key),
            ).fetchone()
        return dict(row)

    def update_parametric_rule(
        self, rule_id: int, *, factor: float | None = None, active: bool | None = None,
        note: str | None = None,
    ) -> dict:
        with _LOCK, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM parametric_rules WHERE id = ?", (rule_id,)
            ).fetchone()
            if row is None:
                raise ValueError("La regla no existe.")
            conn.execute(
                "UPDATE parametric_rules SET factor = ?, active = ?, note = ? WHERE id = ?",
                (
                    factor if factor is not None and factor > 0 else row["factor"],
                    int(active) if active is not None else row["active"],
                    note if note is not None else row["note"],
                    rule_id,
                ),
            )
            row = conn.execute(
                "SELECT * FROM parametric_rules WHERE id = ?", (rule_id,)
            ).fetchone()
        return dict(row)

    def delete_parametric_rule(self, rule_id: int) -> bool:
        with _LOCK, self._connect() as conn:
            removed = conn.execute(
                "DELETE FROM parametric_rules WHERE id = ?", (rule_id,)
            ).rowcount
        return bool(removed)

    def list_parametric_rules(self, include_inactive: bool = False) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM parametric_rules"
                + ("" if include_inactive else " WHERE active = 1 AND engine_read = 0")
                + " ORDER BY concept_code, basis"
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------ aliases

    def set_concept_alias(
        self,
        code: str,
        *,
        kind: str,
        ref_id: int | None = None,
        target_code: str | None = None,
        actor: str = "",
        note: str = "",
        project_id: str = "",
        force: bool = False,
    ) -> dict:
        """The taller's own concept for one of ours: a reference row (their
        catálogo: clave, description and P.U. adopted) or a workspace concept
        (their matrix prices it). Workspace-wide, remembered with who and where.
        Units must agree unless ``force`` (with a note saying why)."""
        if kind == "reference":
            if ref_id is None:
                raise ValueError("Falta la referencia.")
            reference = self.get_reference(ref_id)
            if reference is None:
                raise ValueError("la referencia no existe")
            self.adopt_concept_reference(code, ref_id, force=force)
            row = {
                "kind": "reference", "ref_id": ref_id, "target_code": None,
                "clave": reference["clave"], "description": reference["description"],
                "unit": reference["unit"], "price": float(reference["price"]),
                "source": reference["source_name"], "vigencia": reference["source_vigencia"] or "",
            }
        elif kind == "concept":
            if not target_code or target_code == code:
                raise ValueError("Falta el concepto del taller.")
            with self._connect() as conn:
                target = conn.execute(
                    "SELECT * FROM concepts WHERE code = ? AND active = 1", (target_code,)
                ).fetchone()
            if target is None:
                raise ValueError(f"El concepto {target_code} no existe.")
            with self._connect() as conn:
                own = conn.execute("SELECT unit FROM concepts WHERE code = ?", (code,)).fetchone()
            if own is None:
                raise ValueError(f"El concepto {code} no existe.")
            _check_units(code, str(own["unit"]), str(target["unit"]), force)
            self.clear_concept_price(code)
            row = {
                "kind": "concept", "ref_id": None, "target_code": target_code,
                "clave": target_code, "description": target["description"],
                "unit": target["unit"], "price": None, "source": "matriz del taller",
                "vigencia": "",
            }
        else:
            raise ValueError("Tipo de alias inválido.")
        with _LOCK, self._connect() as conn:
            if conn.execute("SELECT 1 FROM concepts WHERE code = ?", (code,)).fetchone() is None:
                raise ValueError(f"El concepto {code} no existe.")
            conn.execute(
                "INSERT INTO concept_aliases (concept_code, kind, ref_id, target_code, clave, "
                "description, unit, price, source, vigencia, actor, note, project_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(concept_code) DO UPDATE SET kind = excluded.kind, "
                "ref_id = excluded.ref_id, target_code = excluded.target_code, "
                "clave = excluded.clave, description = excluded.description, "
                "unit = excluded.unit, price = excluded.price, source = excluded.source, "
                "vigencia = excluded.vigencia, actor = excluded.actor, note = excluded.note, "
                "project_id = excluded.project_id, created_at = excluded.created_at",
                (
                    code, row["kind"], row["ref_id"], row["target_code"], row["clave"],
                    row["description"], row["unit"], row["price"], row["source"],
                    row["vigencia"], actor, note, project_id, _now(),
                ),
            )
            saved = conn.execute(
                "SELECT * FROM concept_aliases WHERE concept_code = ?", (code,)
            ).fetchone()
        return dict(saved)

    def clear_concept_alias(self, code: str) -> bool:
        with _LOCK, self._connect() as conn:
            removed = conn.execute(
                "DELETE FROM concept_aliases WHERE concept_code = ?", (code,)
            ).rowcount
        if removed:
            self.clear_concept_price(code)
        return bool(removed)

    def load_concept_aliases(self) -> dict[str, dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM concept_aliases").fetchall()
        return {row["concept_code"]: dict(row) for row in rows}

    def list_reference_rows(self, source_keys: list[str] | None = None) -> list[dict]:
        """Every row of the given sources (or of all), for matching."""
        with self._connect() as conn:
            if source_keys:
                marks = ",".join("?" for _ in source_keys)
                rows = conn.execute(
                    "SELECT r.*, s.name AS source_name, s.vigencia AS source_vigencia, "
                    "s.region AS source_region FROM reference_prices r "
                    "JOIN price_sources s ON s.source_key = r.source_key "
                    f"WHERE r.source_key IN ({marks})",
                    tuple(source_keys),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT r.*, s.name AS source_name, s.vigencia AS source_vigencia, "
                    "s.region AS source_region FROM reference_prices r "
                    "JOIN price_sources s ON s.source_key = r.source_key"
                ).fetchall()
        return [self._reference_row(row) for row in rows]

    def clear_concept_price(self, code: str) -> dict:
        with _LOCK, self._connect() as conn:
            conn.execute(
                "UPDATE concepts SET price_override = NULL, price_source_key = NULL, "
                "price_source = NULL, price_clave = NULL, price_vigencia = NULL WHERE code = ?",
                (code,),
            )
            row = conn.execute("SELECT * FROM concepts WHERE code = ?", (code,)).fetchone()
        if row is None:
            raise ValueError(f"El concepto {code} no existe.")
        return dict(row)

    def load_concept_prices(self) -> dict[str, dict]:
        """Adopted precios unitarios by concept code, with provenance."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT c.code, c.price_override, c.price_source_key, c.price_source, "
                "c.price_clave, c.price_vigencia, s.kind AS source_kind FROM concepts c "
                "LEFT JOIN price_sources s ON s.source_key = c.price_source_key "
                "WHERE c.price_override IS NOT NULL AND c.active = 1"
            ).fetchall()
        return {
            row["code"]: {
                "price": float(row["price_override"]), "source_key": row["price_source_key"],
                "source": row["price_source"], "clave": row["price_clave"],
                "vigencia": row["price_vigencia"],
                # Qué incluye ese precio. Un destajo no trae material, y el
                # presupuesto tiene que decirlo donde se lee, no en la ficha
                # de la fuente.
                "alcance": row["source_kind"] or "precios_unitarios",
            }
            for row in rows
        }

    @staticmethod
    def _sync_builtin_concepts(conn: sqlite3.Connection, codes: tuple[str, ...]) -> None:
        """Built-in (rule-bound) concepts added after v2, with their reference
        matrices. OR IGNORE: a taller that already defined the code keeps its own."""
        for index, concept in enumerate(build_default_catalog(CostingAssumptions())):
            if concept.code not in codes:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO concepts (code, description, unit, phase, "
                "production_rate_per_day, rule_key, sequence_order) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (concept.code, concept.description, concept.unit, concept.phase,
                 concept.production_rate_per_day,
                 concept.code if concept.rule is not None else None, index * 10),
            )
            for resource_code, quantity in APU_TEMPLATES.get(concept.code, []):
                conn.execute(
                    "INSERT OR IGNORE INTO apu_components "
                    "(concept_code, resource_code, quantity) VALUES (?, ?, ?)",
                    (concept.code, resource_code, quantity),
                )

    @staticmethod
    def _seed_concepts(conn: sqlite3.Connection, concepts: list, base_order: int) -> None:
        for code, description, unit, phase, rate, order, components in concepts:
            conn.execute(
                "INSERT OR IGNORE INTO concepts (code, description, unit, phase, "
                "production_rate_per_day, rule_key, sequence_order) "
                "VALUES (?, ?, ?, ?, ?, NULL, ?)",
                (code, description, unit, phase, rate, base_order + order),
            )
            for resource_code, quantity in components:
                conn.execute(
                    "INSERT OR IGNORE INTO apu_components "
                    "(concept_code, resource_code, quantity) VALUES (?, ?, ?)",
                    (code, resource_code, quantity),
                )

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
        import_source: str = "",
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
                "production_rate_per_day, rule_key, import_source) "
                "VALUES (?, ?, ?, ?, ?, NULL, ?)",
                (code, description, unit, phase, production_rate_per_day, import_source),
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

    def price_vigencias(self) -> dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT code, vigencia FROM insumos").fetchall()
        return {row["code"]: str(row["vigencia"] or "") for row in rows}

    INDICES_KEY = "price_indices"

    def load_indices(self) -> dict:
        """The taller's table of monthly index values {YYYY-MM: value} and its source."""
        return self.get_setting(self.INDICES_KEY) or {"source": "", "values": {}}

    def save_indices(self, source: str, values: dict[str, float]) -> dict:
        clean = {
            k[:7]: float(v) for k, v in values.items()
            if len(k) >= 7 and k[4] == "-" and float(v) > 0
        }
        payload = {"source": source[:200], "values": dict(sorted(clean.items()))}
        self.set_setting(self.INDICES_KEY, payload)
        return payload

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

    def delete_source(self, source_key: str) -> dict:
        """Quitar una fuente importada y sus renglones.

        Se niega mientras algún concepto tenga adoptado un precio de ella: el
        presupuesto quedaría citando una procedencia que ya no existe, que es
        peor que no citar ninguna. Devuelve qué conceptos lo impiden para que
        se puedan soltar primero."""
        with _LOCK, self._connect() as conn:
            fuente = conn.execute(
                "SELECT * FROM price_sources WHERE source_key = ?", (source_key,)
            ).fetchone()
            if fuente is None:
                raise ValueError(f"La fuente {source_key} no existe.")
            usada = [
                row["code"] for row in conn.execute(
                    "SELECT code FROM concepts WHERE price_source_key = ? AND active = 1",
                    (source_key,),
                ).fetchall()
            ]
            if usada:
                raise ValueError(
                    f"{len(usada)} conceptos tienen precio adoptado de esta fuente "
                    f"({', '.join(sorted(usada)[:6])}). Suéltalos antes de quitarla."
                )
            borrados = conn.execute(
                "DELETE FROM reference_prices WHERE source_key = ?", (source_key,)
            ).rowcount
            conn.execute("DELETE FROM price_sources WHERE source_key = ?", (source_key,))
        return {"source_key": source_key, "name": fuente["name"], "rows": borrados}

    def list_imports(self) -> list[dict]:
        """Las importaciones de matrices que se pueden deshacer, con su peso.

        Sin esta lista, deshacer una importación exige recordar cómo se llamó
        el archivo — y quien importó mal casi nunca lo recuerda."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT import_source AS source, COUNT(*) AS concepts, "
                "SUM(CASE WHEN price_override IS NOT NULL THEN 1 ELSE 0 END) AS with_price "
                "FROM concepts WHERE import_source != '' AND active = 1 "
                "GROUP BY import_source ORDER BY import_source"
            ).fetchall()
        return [dict(row) for row in rows]

    def undo_import(self, source: str) -> dict:
        """Deshacer una importación de matrices: quita los conceptos que creó.

        Una importación mal hecha —claves de cuadrilla entrando como conceptos
        presupuestables, una zona que no era— hoy se quedaba para siempre. Sólo
        se van los que nacieron de esa importación: los conceptos del motor y
        los que el taller escribió a mano nunca se tocan, y uno con precio
        adoptado tampoco, porque algún presupuesto lo está citando."""
        with _LOCK, self._connect() as conn:
            candidatos = [
                dict(row) for row in conn.execute(
                    "SELECT code, price_override FROM concepts "
                    "WHERE import_source = ? AND active = 1",
                    (source,),
                ).fetchall()
            ]
            if not candidatos:
                raise ValueError(f"No hay conceptos importados de «{source}».")
            con_precio = [c["code"] for c in candidatos if c["price_override"] is not None]
            quitables = [c["code"] for c in candidatos if c["price_override"] is None]
            for code in quitables:
                conn.execute("DELETE FROM apu_components WHERE concept_code = ?", (code,))
                conn.execute("DELETE FROM concepts WHERE code = ?", (code,))
        return {
            "source": source, "removed": len(quitables),
            "kept_with_price": sorted(con_precio),
        }

    def list_sources(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM price_sources ORDER BY vigencia DESC, name"
            ).fetchall()
        return [dict(row) for row in rows]

    def import_matrices(self, parse: object, source: str) -> dict:
        """Concepts with their matrices from an OPUS/Neodata export: insumos
        are upserted as cotización of `source` (a % insumo maps to the
        EQ-HERRAMIENTA fraction), existing concepts keep their rule and take
        the imported description, unit and matrix; new ones are manual."""
        from klave_engine.costing.sources.matrices import MatricesParse

        assert isinstance(parse, MatricesParse)
        vigencia = _now()[:7]
        upserted = 0
        previos = {row["code"]: row for row in self.list_insumos()}
        pisados: list[str] = []
        for insumo in parse.insumos.values():
            if insumo.is_labor_percentage:
                continue
            # La misma clave puede venir de dos catálogos con precios
            # distintos: la cuadrilla «1A» vale $615 en el norte y $540 en el
            # sur, y las matrices de cada zona la usan esperando la suya. El
            # último import gana —no hay dónde guardar dos— pero callarlo
            # dejaría las matrices de la otra zona costeando con el precio
            # equivocado sin que nadie lo supiera.
            previo = previos.get(insumo.code)
            if (
                previo is not None
                and (previo.get("source") or "") not in ("", source)
                and abs(float(previo.get("unit_cost") or 0) - insumo.unit_cost) > 0.01
            ):
                pisados.append(
                    f"{insumo.code}: ${float(previo['unit_cost']):,.2f} de "
                    f"«{previo['source']}» → ${insumo.unit_cost:,.2f} de «{source}»"
                )
            self.upsert_insumo(
                insumo.code, description=insumo.description, unit=insumo.unit,
                resource_type=insumo.resource_type, unit_cost=insumo.unit_cost,
                source=source, source_type="cotizacion", region="MX", vigencia=vigencia,
            )
            upserted += 1
        created = updated = 0
        problems = list(parse.problems)
        if pisados:
            problems.append(
                f"{len(pisados)} insumos cambiaron de precio al venir de otro catálogo "
                f"({'; '.join(pisados[:4])}"
                f"{'…' if len(pisados) > 4 else ''}). Las matrices que ya los usaban "
                "quedan costeando con el precio nuevo."
            )
        existing_codes = {c["code"] for c in self.load_concepts(include_inactive=True)}
        for concept in parse.concepts:
            # Una matriz puede traer varios cargos porcentuales distintos
            # —herramienta menor 3 % y andamios 3 %— y todos se cobran sobre
            # la mano de obra. Al colapsarlos en EQ-HERRAMIENTA se suman: dos
            # cargos del 3 % son 6 % de la mano de obra, no 3 % dos veces
            # (que además choca con la clave única de la matriz).
            acumulado: dict[str, float] = {}
            orden: list[str] = []
            for code, quantity in concept.components:
                resource = parse.insumos.get(code)
                if resource is not None and resource.is_labor_percentage:
                    clave = "EQ-HERRAMIENTA"
                    valor = quantity / 100 if quantity > 1 else quantity
                else:
                    clave, valor = code, quantity
                if clave not in acumulado:
                    orden.append(clave)
                acumulado[clave] = round(acumulado.get(clave, 0.0) + valor, 8)
            components: list[tuple[str, float]] = [(c, acumulado[c]) for c in orden]
            rate = concept.production_rate_per_day or 10.0
            try:
                if concept.code in existing_codes:
                    self.update_concept(
                        concept.code, description=concept.description, unit=concept.unit,
                        phase=concept.phase, production_rate_per_day=rate,
                    )
                    self.set_apu_components(concept.code, components)
                    updated += 1
                else:
                    self.create_concept(
                        code=concept.code, description=concept.description, unit=concept.unit,
                        phase=concept.phase, production_rate_per_day=rate,
                        components=components, import_source=source,
                    )
                    created += 1
            except ValueError as exc:
                problems.append(f"{concept.code}: {exc}")
        return {
            "concepts_created": created, "concepts_updated": updated,
            "insumos_upserted": upserted, "problems": problems, "source": source,
        }

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

    def adopt_reference(self, insumo_code: str, ref_id: int, *, force: bool = False) -> dict:
        """Price an insumo from a published row, carrying the publication,
        clave, region and vigencia as provenance. The row's unit must be the
        insumo's unless forced knowingly."""
        reference = self.get_reference(ref_id)
        if reference is None:
            raise ValueError("la referencia no existe")
        with self._connect() as conn:
            insumo = conn.execute(
                "SELECT unit FROM insumos WHERE code = ?", (insumo_code,)
            ).fetchone()
        if insumo is None:
            raise ValueError(f"El insumo {insumo_code} no existe.")
        _check_units(insumo_code, str(insumo["unit"]), str(reference["unit"]), force)
        return self.upsert_insumo(
            insumo_code,
            unit_cost=float(reference["price"]),
            source=f"{reference['source_name']} · {reference['clave']}",
            source_type="publicacion",
            region=reference["source_region"],
            vigencia=reference["source_vigencia"],
        )

    # ------------------------------------------------- levantamiento mappings

    def list_inventory_mappings(self) -> list[dict]:
        """Symbol/layer → concept rules of the workspace: a block name or a
        layer name (exact, case-insensitive) feeds a concept at `factor`
        units per symbol or per metre."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM inventory_mappings ORDER BY kind, pattern"
            ).fetchall()
        return [dict(row) for row in rows]

    def add_inventory_mapping(
        self, *, kind: str, pattern: str, concept_code: str, factor: float = 1.0
    ) -> dict:
        if kind not in ("block", "layer", "tag", "area"):
            raise ValueError("kind debe ser block, layer, tag o area")
        if not pattern.strip():
            raise ValueError("El patrón no puede estar vacío.")
        if factor <= 0:
            raise ValueError("El factor debe ser positivo.")
        with _LOCK, self._connect() as conn:
            if conn.execute(
                "SELECT 1 FROM concepts WHERE code = ?", (concept_code,)
            ).fetchone() is None:
                raise ValueError(f"El concepto {concept_code} no existe.")
            conn.execute(
                "INSERT INTO inventory_mappings (kind, pattern, concept_code, factor, created_at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(kind, pattern) DO UPDATE SET "
                "concept_code = excluded.concept_code, factor = excluded.factor, "
                "created_at = excluded.created_at",
                (kind, pattern.strip(), concept_code, float(factor), _now()),
            )
            row = conn.execute(
                "SELECT * FROM inventory_mappings WHERE kind = ? AND pattern = ?",
                (kind, pattern.strip()),
            ).fetchone()
        return dict(row)

    def delete_inventory_mapping(self, mapping_id: int) -> bool:
        with _LOCK, self._connect() as conn:
            cursor = conn.execute("DELETE FROM inventory_mappings WHERE id = ?", (mapping_id,))
        return cursor.rowcount > 0

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


def get_catalog_store(data_dir: Path, workspace_id: str | None = None) -> CatalogStore:
    """One store per taller (``catalogs/<workspace_id>.db``); without a
    workspace — the open, local-first mode — the single legacy file."""
    path = (
        (data_dir / "catalogs" / f"{workspace_id}.db")
        if workspace_id
        else (data_dir / CATALOG_DB_FILENAME)
    ).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        store = _STORES.get(path)
    if store is None:
        store = CatalogStore(path)
        store.workspace_id = workspace_id
        with _LOCK:
            _STORES[path] = store
    return store
