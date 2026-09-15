"""La base nativa de OPUS: las tablas Visual FoxPro (.DBF/.FPT) que OPUS
guarda por obra o por catálogo, leídas directo — sin pasar por el Excel.

Lo que el Excel pierde y la base trae: la matriz completa con rendimiento
por recurso, las cuadrillas como mano de obra compuesta, los auxiliares
(básicos), el porcentaje de herramienta sobre la mano de obra, el árbol
capítulo → subcapítulo → concepto del presupuesto, el FSR con su
formulación y los costos horarios con sus parámetros.

Una base OPUS es una carpeta con el mismo prefijo y varios sufijos:

  <BASE>P.DBF/.FPT   elementos: insumos y conceptos (PREFIJO dice el tipo)
  <BASE>F.DBF        matrices: renglones (matriz, componente, cantidad)
  <BASE>1.DBF        presupuesto: árbol con nivel y padre (PRE_*)
  <BASE>3.DBF/.FPT   presupuesto: descripciones de cada nodo del árbol
  <BASE>N.DBF        por concepto: indirectos, financiamiento, utilidad
  <BASE>8.DBF        FSR: el cálculo del factor de salario real
  <BASE>J.DBF        costos horarios de equipo
  <BASE>V.*, <BASE>I.*, <BASE>U.*, FRENTES, TIPOSINS  formatos y catálogos
                     de OPUS — no se leen

Los .CDX son índices y no hacen falta. El lector no depende de ninguna
librería: DBF es un formato de registros fijos y FPT una lista de bloques.

Lo que NO se traduce se dice: el modelo de Klave no anida básicos, así que
una cuadrilla o un auxiliar entra como insumo con su precio compuesto y
el aviso lo declara; el rendimiento por día se DERIVA de las jornadas de
mano de obra por unidad (OPUS no lo guarda), y se declara derivado.
"""

from __future__ import annotations

import io
import struct
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass, field

from klave_engine.costing.sources.custom import CustomCatalogError
from klave_engine.costing.sources.matrices import ConceptRow, InsumoRow, MatricesParse

# PREFIJO en la tabla de elementos (TIPOSINS.DBF lo publica, es fijo en OPUS).
PREFIJO_MATERIAL = 1
PREFIJO_MANO_DE_OBRA = 2
PREFIJO_HERRAMIENTA = 4
PREFIJO_EQUIPO = 8
PREFIJO_AUXILIAR = 16
PREFIJO_CONCEPTO = 32

_LABOR_UNITS = ("JOR", "JORNADA", "JOR.", "DIA", "DÍA")


# ------------------------------------------------------------------ DBF / FPT

def read_dbf(raw: bytes) -> tuple[list[tuple[str, str, int, int]], list[dict]]:
    """Registros de un .DBF (dBASE/FoxPro) como diccionarios; los borrados se
    omiten. Los campos memo (M) devuelven el índice de bloque en el .FPT."""
    if len(raw) < 32:
        raise CustomCatalogError("La tabla DBF está truncada.")
    nrec = struct.unpack("<I", raw[4:8])[0]
    hlen = struct.unpack("<H", raw[8:10])[0]
    rlen = struct.unpack("<H", raw[10:12])[0]
    fields: list[tuple[str, str, int, int]] = []
    pos = 32
    while pos < hlen and raw[pos] != 0x0D:
        fd = raw[pos:pos + 32]
        name = fd[:11].split(b"\x00")[0].decode("latin1")
        fields.append((name, chr(fd[11]), fd[16], fd[17]))
        pos += 32
    rows: list[dict] = []
    pos = hlen
    for _ in range(nrec):
        rec = raw[pos:pos + rlen]
        pos += rlen
        if len(rec) < rlen:
            break
        if rec[0:1] == b"*":
            continue
        cursor = 1
        row: dict = {}
        for name, typ, ln, _dec in fields:
            cell = rec[cursor:cursor + ln]
            cursor += ln
            if typ in ("C", "D"):
                row[name] = cell.decode("latin1").strip()
            elif typ == "N" or typ == "F":
                text = cell.decode("latin1").strip()
                try:
                    row[name] = float(text) if text else None
                except ValueError:
                    row[name] = None
            elif typ == "L":
                row[name] = cell in (b"T", b"t", b"Y", b"y")
            elif typ == "M":
                text = cell.decode("latin1").strip()
                if text.isdigit():
                    row[name] = int(text)
                elif ln == 4:
                    row[name] = struct.unpack("<I", cell)[0]
                else:
                    row[name] = 0
            else:
                row[name] = cell
        rows.append(row)
    return fields, rows


def memo_reader(raw: bytes | None):
    """Lector de memos de un .FPT (FoxPro): bloque → texto. Sin archivo, todo
    memo es vacío — la descripción corta del DBF sigue disponible."""
    if not raw or len(raw) < 8:
        return lambda _index: ""
    block = struct.unpack(">H", raw[6:8])[0] or 64

    def memo(index: int) -> str:
        if not index:
            return ""
        offset = index * block
        if offset + 8 > len(raw):
            return ""
        length = struct.unpack(">I", raw[offset + 4:offset + 8])[0]
        return raw[offset + 8:offset + 8 + length].decode("latin1").replace("\r\n", "\n").strip()

    return memo


# ------------------------------------------------------------------ la base

@dataclass
class OpusCostoHorario:
    code: str
    costo_base: float
    vida_util_horas: float
    horas_anuales: float
    tasa_interes: float
    seguro: float
    mantenimiento: float
    costo_horario: float


@dataclass
class OpusExtras:
    """Lo que la base trae además de las matrices; informativo por ahora."""
    fsr: float | None = None
    indirectos_pct: float | None = None
    financiamiento_pct: float | None = None
    utilidad_pct: float | None = None
    costos_horarios: list[OpusCostoHorario] = field(default_factory=list)
    capitulos: list[str] = field(default_factory=list)
    cuadrillas: int = 0
    auxiliares: int = 0


@dataclass
class OpusParse:
    matrices: MatricesParse
    extras: OpusExtras


def _suffix_map(files: Mapping[str, bytes]) -> dict[str, bytes]:
    """Los archivos por sufijo (P.DBF, F.DBF, 3.FPT…), sin el prefijo de la
    base. El prefijo es el nombre más largo común a los .DBF con sufijo
    de una letra o dígito; FRENTES y TIPOSINS quedan fuera."""
    names = {name.rsplit("/", 1)[-1].upper(): data for name, data in files.items()}
    shared = ("FRENTES.DBF", "TIPOSINS.DBF")
    candidates = [n[:-4] for n in names if n.endswith(".DBF") and n not in shared]
    if not candidates:
        raise CustomCatalogError(
            "No hay tablas .DBF de OPUS en el archivo (se esperaba la carpeta de la base con "
            "sus .DBF y .FPT)."
        )
    # El prefijo común a todas las tablas; la tabla raíz (<BASE>.DBF) es el
    # prefijo mismo y las demás llevan una letra o dígito de sufijo.
    prefix = candidates[0]
    for stem in candidates[1:]:
        while prefix and not stem.startswith(prefix):
            prefix = prefix[:-1]
    if not prefix:
        raise CustomCatalogError("Las tablas .DBF no comparten el prefijo de una base OPUS.")
    out: dict[str, bytes] = {}
    for name, data in names.items():
        if name.startswith(prefix):
            out[name[len(prefix):]] = data
    return out


def _parent_key(node: dict) -> int:
    value = node.get("PRE_IDPAD")
    return int(value) if value is not None else -1


def _unit(value: str | None) -> str:
    text = (value or "").strip().upper().replace("M²", "M2").replace("M³", "M3")
    return text or "PZA"


def _resource_type(prefijo: int) -> str:
    if prefijo == PREFIJO_MANO_DE_OBRA:
        return "mano_de_obra"
    if prefijo in (PREFIJO_EQUIPO, PREFIJO_HERRAMIENTA):
        return "equipo"
    return "material"


def parse_opus_native(files: Mapping[str, bytes]) -> OpusParse:
    """La base OPUS (nombre → bytes de cada archivo) como conceptos con sus
    matrices, más lo que la base declara y Klave todavía no modela."""
    tables = _suffix_map(files)
    if "P.DBF" not in tables or "F.DBF" not in tables:
        raise CustomCatalogError(
            "La base OPUS necesita al menos las tablas de elementos (…P.DBF) y de "
            "matrices (…F.DBF)."
        )
    _, elements = read_dbf(tables["P.DBF"])
    memo_p = memo_reader(tables.get("P.FPT"))
    _, components = read_dbf(tables["F.DBF"])

    problems: list[str] = []
    extras = OpusExtras()
    insumos: dict[str, InsumoRow] = {}
    concept_meta: dict[str, dict] = {}
    for row in elements:
        prefijo = int(row.get("PREFIJO") or 0)
        code = (row.get("NOMBRE") or "").strip().upper()
        if not code:
            continue
        description = memo_p(row.get("DESCRIPCIO") or 0) or (row.get("DESCCORTA") or "") or code
        description = " ".join(description.split())
        unit_raw = (row.get("UNIDAD") or "").strip()
        price = float(row.get("PRECIO") or 0.0)
        if prefijo == PREFIJO_CONCEPTO:
            concept_meta[code] = {
                "description": description, "unit": _unit(unit_raw), "price": price,
            }
            continue
        if prefijo not in (PREFIJO_MATERIAL, PREFIJO_MANO_DE_OBRA, PREFIJO_HERRAMIENTA,
                           PREFIJO_EQUIPO, PREFIJO_AUXILIAR):
            continue
        # «C.F. EQX» es el cargo fijo de un equipo, un renglón contable de OPUS
        # que no es un recurso de matriz.
        if code.startswith("C.F."):
            continue
        is_pct = unit_raw.strip().upper().startswith("(%)") or unit_raw.strip() == "%" \
            or code.startswith("%")
        if prefijo == PREFIJO_MANO_DE_OBRA and bool(row.get("BASICO")):
            extras.cuadrillas += 1
        if prefijo == PREFIJO_AUXILIAR:
            extras.auxiliares += 1
        if not is_pct and price <= 0:
            problems.append(
                f"Insumo {code} sin costo (por cotización); las matrices que lo usan quedan "
                "sin ese recurso."
            )
            continue
        insumos[code] = InsumoRow(
            code=code, description=description, unit=_unit(unit_raw) if not is_pct else "%",
            unit_cost=price, resource_type=_resource_type(prefijo),
            is_labor_percentage=is_pct,
        )

    # Las fases: subcapítulo del árbol del presupuesto, si la base lo trae.
    phase_of: dict[str, str] = {}
    if "1.DBF" in tables and "3.DBF" in tables:
        _, tree = read_dbf(tables["1.DBF"])
        _, nodes = read_dbf(tables["3.DBF"])
        memo_3 = memo_reader(tables.get("3.FPT"))
        text_by_id = {
            int(n.get("ID") or 0): " ".join((memo_3(n.get("DESCRIPCIO") or 0) or "").split())
            for n in nodes
        }
        # PRE_IDPAD apunta al PRE_IDUNI del padre; el texto vive en la tabla
        # 3 bajo el mismo ID que PRE_ID.
        by_uni = {int(t.get("PRE_IDUNI") or 0): t for t in tree}
        for node in tree:
            code = (node.get("PRE_COM") or "").strip().upper()
            if not code:
                continue
            parent = by_uni.get(_parent_key(node))
            label = ""
            hops = 0
            while parent is not None and hops < 9:
                label = text_by_id.get(int(parent.get("PRE_ID") or 0), "")
                if label:
                    break
                parent = by_uni.get(_parent_key(parent))
                hops += 1
            if label:
                phase_of[code] = label[:60]
        extras.capitulos = sorted(
            {text_by_id[int(t.get("PRE_ID") or 0)] for t in tree
             if int(t.get("PRE_NIVEL") or 0) == 1 and text_by_id.get(int(t.get("PRE_ID") or 0))}
        )

    # Las matrices: cada renglón es (matriz, componente, cantidad por unidad).
    rows_by_matrix: dict[str, list[dict]] = {}
    for row in components:
        name = (row.get("NOMBRE") or "").strip().upper()
        if name:
            rows_by_matrix.setdefault(name, []).append(row)

    concepts: list[ConceptRow] = []
    for code, meta in concept_meta.items():
        rows = rows_by_matrix.get(code, [])
        comps: list[tuple[str, float]] = []
        labor_days = 0.0
        for row in rows:
            comp = (row.get("COMPONENTE") or "").strip().upper()
            qty = row.get("CANTIDAD")
            if not comp or qty is None or qty <= 0:
                continue
            if comp.startswith("C.F."):
                continue
            if comp not in insumos:
                if comp in concept_meta:
                    # Un concepto usado como recurso (subcontrato o concepto
                    # auxiliar): entra como material a su precio.
                    insumos[comp] = InsumoRow(
                        code=comp, description=concept_meta[comp]["description"],
                        unit=concept_meta[comp]["unit"], unit_cost=concept_meta[comp]["price"],
                        resource_type="material",
                    )
                else:
                    problems.append(f"{code}: recurso {comp} no existe en la tabla de elementos.")
                    continue
            comps.append((comp, float(qty)))
            resource = insumos[comp]
            if resource.resource_type == "mano_de_obra" and resource.unit in _LABOR_UNITS:
                labor_days += float(qty)
        if not comps:
            problems.append(f"Concepto {code} sin matriz en la base: no se importa.")
            continue
        rate = round(1.0 / labor_days, 4) if labor_days > 0 else None
        concepts.append(ConceptRow(
            code=code, description=meta["description"], unit=meta["unit"],
            phase=phase_of.get(code, "Sin partida"), production_rate_per_day=rate,
            components=comps,
        ))
    if not concepts:
        raise CustomCatalogError("La base OPUS no trae conceptos con matriz; nada que importar.")

    if extras.cuadrillas or extras.auxiliares:
        problems.append(
            f"{extras.cuadrillas} cuadrillas y {extras.auxiliares} auxiliares entran como insumos "
            "con su precio compuesto: Klave no anida básicos todavía."
        )
    derived = sum(1 for c in concepts if c.production_rate_per_day is not None)
    if derived:
        problems.append(
            f"El rendimiento por día de {derived} conceptos se derivó de las jornadas de mano de "
            "obra por unidad (OPUS no lo guarda); los demás toman el rendimiento por omisión."
        )

    # Lo demás que la base declara.
    if "N.DBF" in tables:
        _, integ = read_dbf(tables["N.DBF"])
        first = next((r for r in integ if r.get("INDIRECTOS") is not None), None)
        if first is not None:
            extras.indirectos_pct = float(first.get("INDIRECTOS") or 0)
            extras.financiamiento_pct = float(first.get("FINANCIA") or 0)
            extras.utilidad_pct = float(first.get("UTILIDAD") or 0)
    if "8.DBF" in tables:
        _, fsr_rows = read_dbf(tables["8.DBF"])
        if fsr_rows and fsr_rows[0].get("FSR_FSR"):
            extras.fsr = round(float(fsr_rows[0]["FSR_FSR"]), 5)
    if "J.DBF" in tables:
        _, eq_rows = read_dbf(tables["J.DBF"])
        for r in eq_rows:
            name = (r.get("NOMBRE") or "").strip().upper()
            if not name:
                continue
            extras.costos_horarios.append(OpusCostoHorario(
                code=name, costo_base=float(r.get("COSTO_BASE") or 0),
                vida_util_horas=float(r.get("VIDA_UTIL") or 0),
                horas_anuales=float(r.get("HORAS_AN") or 0),
                tasa_interes=float(r.get("TASA_INTER") or 0), seguro=float(r.get("SEGURO") or 0),
                mantenimiento=float(r.get("MANTENIMIE") or 0),
                costo_horario=float(r.get("TOTAL") or r.get("RENTA_HORA") or 0),
            ))

    return OpusParse(
        matrices=MatricesParse(concepts=concepts, insumos=insumos, problems=problems),
        extras=extras,
    )


def is_opus_zip(raw: bytes, filename: str = "") -> bool:
    """Un .zip con tablas .DBF adentro es una base OPUS; un XLSX también
    empieza por PK, así que se mira el contenido, no la extensión."""
    if raw[:2] != b"PK":
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            return any(n.upper().endswith(".DBF") for n in zf.namelist())
    except zipfile.BadZipFile:
        return False


def parse_opus_zip(raw: bytes) -> OpusParse:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            files = {
                info.filename: zf.read(info)
                for info in zf.infolist()
                if not info.is_dir() and info.filename.upper().endswith((".DBF", ".FPT"))
            }
    except zipfile.BadZipFile as exc:
        raise CustomCatalogError("El .zip de la base OPUS no se pudo abrir.") from exc
    return parse_opus_native(files)


def extras_summary(extras: OpusExtras) -> dict:
    return {
        "fsr": extras.fsr,
        "indirectos_pct": extras.indirectos_pct,
        "financiamiento_pct": extras.financiamiento_pct,
        "utilidad_pct": extras.utilidad_pct,
        "costos_horarios": len(extras.costos_horarios),
        "capitulos": extras.capitulos,
        "cuadrillas": extras.cuadrillas,
        "auxiliares": extras.auxiliares,
    }
