"""La base nativa de OPUS (.DBF/.FPT) se lee directo: elementos por tipo,
matrices con cantidad por unidad, fases del árbol del presupuesto, el
rendimiento derivado de la mano de obra y lo que la base declara además."""

import io
import struct
import zipfile

import pytest
from klave_engine.costing.catalog_store import get_catalog_store
from klave_engine.costing.sources.custom import CustomCatalogError
from klave_engine.costing.sources.opus_native import (
    extras_summary,
    is_opus_zip,
    parse_opus_native,
    parse_opus_zip,
    read_dbf,
)

# ------------------------------------------------------------ un escritor mínimo


def write_dbf(fields: list[tuple[str, str, int, int]], rows: list[dict]) -> bytes:
    """Un .DBF de FoxPro con los tipos que OPUS usa (C, N, L, M, D)."""
    rlen = 1 + sum(f[2] for f in fields)
    hlen = 32 + 32 * len(fields) + 1
    out = bytearray()
    out += bytes([0xF5, 26, 5, 11]) + struct.pack("<IHH", len(rows), hlen, rlen) + bytes(20)
    for name, typ, ln, dec in fields:
        fd = bytearray(32)
        fd[:len(name)] = name.encode("latin1")
        fd[11] = ord(typ)
        fd[16] = ln
        fd[17] = dec
        out += fd
    out += b"\x0D"
    for row in rows:
        out += b" "
        for name, typ, ln, dec in fields:
            value = row.get(name)
            if typ == "C" or typ == "D":
                out += str(value or "").encode("latin1")[:ln].ljust(ln)
            elif typ == "N":
                text = "" if value is None else (f"{value:.{dec}f}" if dec else str(int(value)))
                out += text.encode("latin1").rjust(ln)
            elif typ == "L":
                out += b"T" if value else b"F"
            elif typ == "M":
                out += str(value or "").encode("latin1").rjust(ln)
    out += b"\x1A"
    return bytes(out)


def write_fpt(memos: list[str], block: int = 64) -> tuple[bytes, list[int]]:
    """Un .FPT con un memo por bloque; devuelve los índices de bloque."""
    out = bytearray(block)  # header block
    out[6:8] = struct.pack(">H", block)
    indexes: list[int] = []
    for text in memos:
        indexes.append(len(out) // block)
        data = text.encode("latin1")
        chunk = struct.pack(">II", 1, len(data)) + data
        padding = (-len(chunk)) % block
        out += chunk + bytes(padding)
    return bytes(out), indexes


ELEMENT_FIELDS = [
    ("PREFIJO", "N", 3, 0), ("NOMBRE", "C", 20, 0), ("UNIDAD", "C", 8, 0),
    ("BASICO", "L", 1, 0), ("PRECIO", "N", 14, 4), ("FSR", "N", 10, 5),
    ("DESCRIPCIO", "M", 10, 0), ("DESCCORTA", "C", 40, 0),
]
MATRIX_FIELDS = [
    ("PREF", "N", 3, 0), ("NOMBRE", "C", 20, 0), ("PREFCOMP", "N", 3, 0),
    ("COMPONENTE", "C", 20, 0), ("NOELE", "N", 6, 2), ("RENDTO", "N", 14, 6),
    ("CANTIDAD", "N", 14, 6), ("COSTO", "N", 14, 4),
]
TREE_FIELDS = [
    ("PRE_ID", "N", 10, 0), ("PRE_IDUNI", "N", 10, 0), ("PRE_NIVEL", "N", 3, 0),
    ("PRE_IDPAD", "N", 10, 0), ("PRE_COM", "C", 20, 0),
]
NODE_FIELDS = [("ID", "N", 10, 0), ("IDUNICO", "N", 10, 0), ("NIVEL", "C", 2, 0),
               ("DESCRIPCIO", "M", 10, 0), ("NOMBRE", "C", 20, 0)]
INTEG_FIELDS = [("NOMBRE", "C", 20, 0), ("INDIRECTOS", "N", 8, 2), ("FINANCIA", "N", 8, 2),
                ("UTILIDAD", "N", 8, 2)]
FSR_FIELDS = [("FSR_CLV", "C", 10, 0), ("FSR_FSR", "N", 12, 5)]
EQ_FIELDS = [("NOMBRE", "C", 20, 0), ("COSTO_BASE", "N", 14, 2), ("VIDA_UTIL", "N", 10, 0),
             ("HORAS_AN", "N", 10, 0), ("SEGURO", "N", 8, 4), ("TASA_INTER", "N", 8, 4),
             ("MANTENIMIE", "N", 8, 4), ("TOTAL", "N", 12, 2), ("RENTA_HORA", "N", 12, 2)]


@pytest.fixture
def base() -> dict[str, bytes]:
    fpt, idx = write_fpt([
        "Placa A-36 de 3/8\"", "Oficial soldador", "Cuadrilla 1 soldador + 2 ayudantes",
        "Herramienta menor", "Equipo de corte oxi-acetileno",
        "Estructura para columnas con placa A-36 3/8\", incluye soldadura y montaje",
        "Concepto sin matriz",
    ])
    elements = write_dbf(ELEMENT_FIELDS, [
        {"PREFIJO": 1, "NOMBRE": "313-APL-0104", "UNIDAD": "ton", "PRECIO": 35200.0,
         "DESCRIPCIO": idx[0]},
        {"PREFIJO": 2, "NOMBRE": "MO091", "UNIDAD": "JOR", "PRECIO": 1748.2, "FSR": 1.84,
         "DESCRIPCIO": idx[1]},
        {"PREFIJO": 2, "NOMBRE": "1S2E", "UNIDAD": "jor", "BASICO": True, "PRECIO": 4130.89,
         "DESCRIPCIO": idx[2]},
        {"PREFIJO": 8, "NOMBRE": "%MO1", "UNIDAD": "(%)MO", "PRECIO": 0.0,
         "DESCRIPCIO": idx[3]},
        {"PREFIJO": 8, "NOMBRE": "EQECORTE", "UNIDAD": "HOR", "PRECIO": 1207.09,
         "DESCRIPCIO": idx[4]},
        {"PREFIJO": 8, "NOMBRE": "C.F. EQECORTE", "UNIDAD": "", "PRECIO": 1207.09},
        {"PREFIJO": 1, "NOMBRE": "SIN-PRECIO", "UNIDAD": "KG", "PRECIO": 0.0,
         "DESCCORTA": "Insumo por cotización"},
        {"PREFIJO": 32, "NOMBRE": "EMC3", "UNIDAD": "ton", "PRECIO": 76548.32,
         "DESCRIPCIO": idx[5]},
        {"PREFIJO": 32, "NOMBRE": "HUECO", "UNIDAD": "PZA", "PRECIO": 10.0,
         "DESCRIPCIO": idx[6]},
    ])
    matrices = write_dbf(MATRIX_FIELDS, [
        {"NOMBRE": "EMC3", "PREFCOMP": 1, "COMPONENTE": "313-APL-0104", "CANTIDAD": 1.034,
         "COSTO": 35200.0},
        {"NOMBRE": "EMC3", "PREFCOMP": 2, "COMPONENTE": "1S2E", "CANTIDAD": 2.5,
         "COSTO": 4130.89},
        {"NOMBRE": "EMC3", "PREFCOMP": 2, "COMPONENTE": "MO091", "CANTIDAD": 0.5,
         "COSTO": 1748.2},
        {"NOMBRE": "EMC3", "PREFCOMP": 8, "COMPONENTE": "%MO1", "CANTIDAD": 0.03},
        {"NOMBRE": "EMC3", "PREFCOMP": 8, "COMPONENTE": "EQECORTE", "CANTIDAD": 1.724,
         "COSTO": 1207.09},
        {"NOMBRE": "EMC3", "PREFCOMP": 8, "COMPONENTE": "C.F. EQECORTE", "CANTIDAD": 1.724},
        {"NOMBRE": "EMC3", "PREFCOMP": 1, "COMPONENTE": "SIN-PRECIO", "CANTIDAD": 2.0},
        {"NOMBRE": "EMC3", "PREFCOMP": 1, "COMPONENTE": "FANTASMA", "CANTIDAD": 1.0},
        # La cuadrilla también tiene su matriz (básico): no es un concepto.
        {"NOMBRE": "1S2E", "PREFCOMP": 2, "COMPONENTE": "MO091", "CANTIDAD": 1.0},
    ])
    tree = write_dbf(TREE_FIELDS, [
        {"PRE_ID": 0, "PRE_IDUNI": 0, "PRE_NIVEL": 0, "PRE_IDPAD": -1, "PRE_COM": ""},
        {"PRE_ID": 10, "PRE_IDUNI": 1, "PRE_NIVEL": 1, "PRE_IDPAD": 0, "PRE_COM": ""},
        {"PRE_ID": 20, "PRE_IDUNI": 2, "PRE_NIVEL": 2, "PRE_IDPAD": 1, "PRE_COM": ""},
        {"PRE_ID": 30, "PRE_IDUNI": 3, "PRE_NIVEL": 3, "PRE_IDPAD": 2, "PRE_COM": "EMC3"},
    ])
    node_fpt, nidx = write_fpt(["", "ESTRUCTURA METALICA", "Estructura por TON", "concepto"])
    nodes = write_dbf(NODE_FIELDS, [
        {"ID": 0, "IDUNICO": 0, "NIVEL": "0", "DESCRIPCIO": nidx[0]},
        {"ID": 10, "IDUNICO": 1, "NIVEL": "1", "DESCRIPCIO": nidx[1]},
        {"ID": 20, "IDUNICO": 2, "NIVEL": "2", "DESCRIPCIO": nidx[2]},
        {"ID": 30, "IDUNICO": 3, "NIVEL": "3", "DESCRIPCIO": nidx[3], "NOMBRE": "EMC3"},
    ])
    integ = write_dbf(INTEG_FIELDS, [
        {"NOMBRE": "EMC3", "INDIRECTOS": 14.5, "FINANCIA": 0.5, "UTILIDAD": 10.0},
    ])
    fsr = write_dbf(FSR_FIELDS, [{"FSR_CLV": "JOR8HR", "FSR_FSR": 1.77196}])
    equipo = write_dbf(EQ_FIELDS, [
        {"NOMBRE": "EQECORTE", "COSTO_BASE": 9832.5, "VIDA_UTIL": 6000, "HORAS_AN": 2000,
         "SEGURO": 0.04, "TASA_INTER": 0.1126, "MANTENIMIE": 0.8, "TOTAL": 3.06,
         "RENTA_HORA": 0},
    ])
    prefix = "ACERO_IGI"
    return {
        f"{prefix}.DBF": write_dbf([("ID", "N", 10, 0)], []),
        f"{prefix}P.DBF": elements, f"{prefix}P.FPT": fpt,
        f"{prefix}F.DBF": matrices,
        f"{prefix}1.DBF": tree, f"{prefix}3.DBF": nodes, f"{prefix}3.FPT": node_fpt,
        f"{prefix}N.DBF": integ, f"{prefix}8.DBF": fsr, f"{prefix}J.DBF": equipo,
        "FRENTES.DBF": write_dbf([("NO", "N", 5, 0)], []),
        "TIPOSINS.DBF": write_dbf([("PREFIJO", "N", 5, 0)], []),
    }


def test_read_dbf_round_trips_types():
    raw = write_dbf(ELEMENT_FIELDS, [
        {"PREFIJO": 2, "NOMBRE": "MO091", "UNIDAD": "JOR", "BASICO": True, "PRECIO": 1748.2,
         "FSR": 1.84, "DESCRIPCIO": 7, "DESCCORTA": "Oficial"},
    ])
    fields, rows = read_dbf(raw)
    assert [f[0] for f in fields][:3] == ["PREFIJO", "NOMBRE", "UNIDAD"]
    row = rows[0]
    assert row["PREFIJO"] == 2 and row["NOMBRE"] == "MO091" and row["BASICO"] is True
    assert row["PRECIO"] == pytest.approx(1748.2) and row["DESCRIPCIO"] == 7


def test_elements_matrices_and_phases_come_through(base):
    parse = parse_opus_native(base)
    m = parse.matrices
    assert [c.code for c in m.concepts] == ["EMC3"]
    emc3 = m.concepts[0]
    assert emc3.unit == "TON" and emc3.phase == "Estructura por TON"
    assert emc3.description.startswith("Estructura para columnas con placa A-36")
    # El cargo fijo, el insumo sin precio y el recurso inexistente no entran.
    assert emc3.components == [
        ("313-APL-0104", 1.034), ("1S2E", 2.5), ("MO091", 0.5), ("%MO1", 0.03),
        ("EQECORTE", 1.724),
    ]
    # 3.0 jornadas por tonelada → 0.3333 ton por día, derivado.
    assert emc3.production_rate_per_day == pytest.approx(0.3333, abs=1e-4)
    assert m.insumos["1S2E"].resource_type == "mano_de_obra"
    assert m.insumos["1S2E"].unit == "JOR" and m.insumos["1S2E"].unit_cost == 4130.89
    assert m.insumos["%MO1"].is_labor_percentage and m.insumos["%MO1"].unit == "%"
    assert m.insumos["EQECORTE"].resource_type == "equipo"
    assert "C.F. EQECORTE" not in m.insumos and "SIN-PRECIO" not in m.insumos
    joined = " ".join(m.problems)
    assert "SIN-PRECIO sin costo" in joined
    assert "FANTASMA no existe" in joined
    assert "HUECO sin matriz" in joined
    assert "1 cuadrillas" in joined and "se derivó" in joined


def test_extras_report_what_the_base_declares(base):
    extras = parse_opus_native(base).extras
    summary = extras_summary(extras)
    assert summary["fsr"] == pytest.approx(1.77196)
    assert summary["indirectos_pct"] == 14.5 and summary["utilidad_pct"] == 10.0
    assert summary["capitulos"] == ["ESTRUCTURA METALICA"]
    assert summary["costos_horarios"] == 1 and summary["cuadrillas"] == 1
    assert extras.costos_horarios[0].costo_horario == pytest.approx(3.06)


def test_zip_dispatch_and_store_import(base, data_dir):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, data in base.items():
            zf.writestr(f"KLAV3-Catalogo/{name}", data)
    raw = buffer.getvalue()
    assert is_opus_zip(raw, "acero.zip")
    assert not is_opus_zip(b"PK\x03\x04not-a-zip", "x.xlsx")
    parse = parse_opus_zip(raw)
    store = get_catalog_store(data_dir)
    result = store.import_matrices(parse.matrices, "PRISMA acero 2026")
    assert result["concepts_created"] == 1
    rows = {r["code"]: r for r in store.load_concepts(include_inactive=True)}
    assert rows["EMC3"]["phase"] == "Estructura por TON"
    assert rows["EMC3"]["unit"] == "TON"
    template = dict(store.load_templates()["EMC3"])
    # El % de herramienta cae en EQ-HERRAMIENTA como fracción de la mano de obra.
    assert template["EQ-HERRAMIENTA"] == pytest.approx(0.03)
    assert template["1S2E"] == 2.5


def test_missing_tables_are_said():
    with pytest.raises(CustomCatalogError, match="elementos"):
        parse_opus_native({"X_IGIF.DBF": write_dbf([("NOMBRE", "C", 5, 0)], [])})
    with pytest.raises(CustomCatalogError, match="No hay tablas"):
        parse_opus_native({"hoja.xlsx": b"PK"})
