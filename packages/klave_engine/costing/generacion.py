"""Matrices generadas: una plantilla por familia, la ficha del texto y una
calculadora que sólo sabe aritmética.

Un concepto sin matriz no tiene precio. Antes la única salida era teclear la
matriz a mano o traerla de una base. Aquí se genera desde la plantilla de su
familia — concreto armado por elemento, cimbra, acero, mampostería,
aplanados, pisos, excavación, relleno, plantilla, tuberías — con las
cantidades derivadas de lo que el texto dice (f'c, sección, espesor,
elemento, material, diámetro) y, donde el texto calla, con el valor usual
del oficio. Cada línea y cada rendimiento dicen de dónde salen: la tabla
curada es un documento con fuentes, no un número mágico. Lo que aquí sale
es una propuesta marcada «generada» que se valida contra el precio publicado
(catalog_store.validate_concept); nunca sustituye una matriz del taller sin
que alguien lo pida.
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources

from klave_engine.costing.ficha import extraer_ficha
from klave_engine.costing.matching import normalize, unit_key

_DIM_RE = re.compile(r"\b(\d{1,3}(?:[.,]\d)?)\s*[x×]\s*(\d{1,3}(?:[.,]\d)?)(?!\s*[x×])\b")
_CM_RE = re.compile(r"\b(\d{1,3}(?:[.,]\d)?)\s*(?:cms?\.?|cent[ií]metros?)\b")
_MM_RE = re.compile(r"\b(\d{1,3})\s*mm\b")
_FRACTION_IN_RE = re.compile(r"\b(\d)\s*/\s*(\d)\s*(?:\"|”|pulg)")
_WHOLE_IN_RE = re.compile(r"\b(\d)\s*(?:\"|”|pulg)")
_INCHES_TO_MM = {
    0.5: 13, 0.75: 19, 1.0: 25, 1.25: 32, 1.5: 38, 2.0: 50, 3.0: 75, 4.0: 100, 6.0: 150,
}

_MATERIAL_LABELS = {
    "PVC-SAN": "PVC sanitario", "CPVC": "CPVC", "COBRE": "cobre tipo M",
    "CONDUIT": "conduit de PVC pesado", "block": "block", "tabique": "tabique",
    "tabicon": "tabicón",
}

# Tabla de proporciones: cemento (toneladas) por m³ de concreto hecho en obra.
_CEMENTO_TON_M3 = [(100, 0.250), (150, 0.300), (200, 0.340), (250, 0.380), (300, 0.420)]


# ------------------------------------------------------------------ evaluador

def _cemento_ton(fc: float) -> float:
    puntos = _CEMENTO_TON_M3
    if fc <= puntos[0][0]:
        return puntos[0][1]
    if fc >= puntos[-1][0]:
        return puntos[-1][1]
    for (fc0, t0), (fc1, t1) in zip(puntos, puntos[1:], strict=False):
        if fc0 <= fc <= fc1:
            return t0 + (t1 - t0) * (fc - fc0) / (fc1 - fc0)
    return puntos[-1][1]


def _piezas_m2(largo_cm: float, alto_cm: float, junta_cm: float = 1.0) -> float:
    return 10000.0 / ((largo_cm + junta_cm) * (alto_cm + junta_cm))


_FUNCIONES: dict[str, Callable[..., float]] = {
    "max": max, "min": min, "cemento_ton": _cemento_ton, "piezas_m2": _piezas_m2,
}
_OPERADORES = {
    ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b,
}


def evaluar(formula: str, variables: dict[str, float]) -> float:
    """Aritmética sobre las variables de la ficha y nada más: números, + − × ÷,
    paréntesis y las funciones de la tabla. Un nombre sin valor es un error
    con nombre, no un cero."""
    try:
        tree = ast.parse(formula.strip(), mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Fórmula inválida «{formula}»: {exc.msg}") from exc

    def walk(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id not in variables or variables[node.id] is None:
                raise ValueError(
                    f"La fórmula «{formula}» necesita «{node.id}» y la ficha no lo da."
                )
            value = variables[node.id]
            if not isinstance(value, (int, float)):
                raise ValueError(f"«{node.id}» no es un número.")
            return float(value)
        if isinstance(node, ast.BinOp) and type(node.op) in _OPERADORES:
            return _OPERADORES[type(node.op)](walk(node.left), walk(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -walk(node.operand)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            fn = _FUNCIONES.get(node.func.id)
            if fn is None:
                raise ValueError(f"Función desconocida «{node.func.id}» en «{formula}».")
            return float(fn(*(walk(arg) for arg in node.args)))
        raise ValueError(f"La fórmula «{formula}» sólo admite aritmética.")

    return walk(tree)


# ------------------------------------------------------------------- ficha

def ficha_numerica(description: str, spec_signature: dict | None = None) -> dict:
    """Lo que el texto dice, en números: f'c, sección b×h, espesor, diámetro,
    elemento, acabado, material. La firma del plano (spec_signature) manda
    sobre el texto cuando la trae."""
    text = description or ""
    low = normalize(text)
    ficha: dict = {"texto": low}
    for dato in extraer_ficha(text):
        campo, valor = dato["campo"], dato["valor"]
        numero = re.match(r"\s*(\d+(?:\.\d+)?)", valor)
        if campo == "f'c" and numero:
            ficha["fc"] = float(numero.group(1))
        elif campo == "fy" and numero:
            ficha["fy"] = float(numero.group(1))
        elif campo == "Espesor" and numero:
            ficha["espesor_cm"] = float(numero.group(1))
        elif campo == "Acabado":
            ficha["acabado"] = "aparente" if "aparente" in valor else "comun"
        elif campo == "Elemento":
            ficha["elemento"] = _elemento_canonico(valor.split(",")[0].strip())
    if "fino" in low:
        ficha["acabado"] = "fino"
    elif "rustico" in low:
        ficha["acabado"] = "rustico"
    if "plafon" in low and "elemento" not in ficha:
        ficha["elemento"] = "plafones"
    m = _DIM_RE.search(low)
    if m:
        ficha["b_cm"] = float(m.group(1).replace(",", "."))
        ficha["h_cm"] = float(m.group(2).replace(",", "."))
    m = _CM_RE.search(low)
    if m:
        ficha["cm"] = float(m.group(1).replace(",", "."))
    diam = _diametro_mm(low)
    if diam is not None:
        ficha["diam_mm"] = diam
    material = _material(low)
    if material:
        ficha["material"] = material
        ficha["material_label"] = _MATERIAL_LABELS.get(material, material)
    for key, value in (spec_signature or {}).items():
        if key == "section_cm" and isinstance(value, (list, tuple)) and len(value) == 2:
            ficha["b_cm"], ficha["h_cm"] = float(value[0]), float(value[1])
        elif key in ("fc", "fy", "espesor_cm", "diam_mm", "b_cm", "h_cm"):
            ficha[key] = float(value)
        elif key in ("elemento", "material", "acabado") and isinstance(value, str):
            ficha[key] = value
            if key == "material":
                ficha["material_label"] = _MATERIAL_LABELS.get(value, value)
    return ficha


def _elemento_canonico(nombre: str) -> str:
    n = normalize(nombre)
    for clave, canon in (
        ("contratrabe", "contratrabes"), ("columna", "columnas"), ("castillo", "castillos"),
        ("trabe", "trabes"), ("losa", "losas"), ("muro", "muros"), ("zapata", "zapatas"),
        ("dala", "dalas"), ("cadena", "dalas"), ("firme", "firmes"), ("pilote", "pilotes"),
        ("pretil", "pretiles"), ("faldon", "pretiles"), ("cimentacion", "cimentacion"),
        ("subestructura", "cimentacion"), ("superestructura", "trabes"),
        ("entrepiso", "losas"), ("azotea", "losas"),
    ):
        if clave in n:
            return canon
    return n


def _diametro_mm(low: str) -> float | None:
    m = _MM_RE.search(low)
    if m:
        return float(m.group(1))
    m = _FRACTION_IN_RE.search(low)
    if m:
        pulgadas = float(m.group(1)) / float(m.group(2))
        return float(_INCHES_TO_MM.get(pulgadas, round(pulgadas * 25.4)))
    m = _WHOLE_IN_RE.search(low)
    if m:
        pulgadas = float(m.group(1))
        return float(_INCHES_TO_MM.get(pulgadas, round(pulgadas * 25.4)))
    return None


def _material(low: str) -> str:
    if "cpvc" in low:
        return "CPVC"
    if "cobre" in low:
        return "COBRE"
    if "conduit" in low or "poliducto" in low:
        return "CONDUIT"
    if "pvc" in low:
        return "PVC-SAN"
    if "tabicon" in low:
        return "tabicon"
    if "tabique" in low or "ladrillo" in low:
        return "tabique"
    if "block" in low:
        return "block"
    return ""


# ---------------------------------------------------------------- plantillas

@dataclass(frozen=True)
class Var:
    formulas: tuple[tuple[str, tuple[str, ...]], ...]
    by: str | None
    table: dict[str, float]
    default: float | None
    source: str


@dataclass(frozen=True)
class Linea:
    resource: str
    formula: str
    source: str
    by_fc: dict[str, str]
    by_material: dict[str, str]
    when_any: tuple[str, ...]
    unless_any: tuple[str, ...]
    materials: tuple[str, ...]
    template: str | None
    template_description: str | None


@dataclass(frozen=True)
class Plantilla:
    key: str
    label: str
    units: tuple[str, ...]
    match_all: tuple[str, ...]
    match_any: tuple[str, ...]
    match_not: tuple[str, ...]
    vars: dict[str, Var]
    lines: tuple[Linea, ...]
    rendimiento: Var
    unit_scale: dict[str, float]


@dataclass(frozen=True)
class CuadrillaDef:
    code: str
    description: str
    members: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class InsumoDef:
    code: str
    description: str
    unit: str
    resource_type: str


@dataclass(frozen=True)
class CategoriaDef:
    code: str
    description: str
    salario_nominal: float


@dataclass(frozen=True)
class LineaGenerada:
    resource_code: str
    quantity: float
    source: str
    formula: str


@dataclass
class Generada:
    plantilla_key: str
    plantilla_label: str
    lines: list[LineaGenerada]
    cuadrillas: list[CuadrillaDef]
    insumos_nuevos: list[InsumoDef]
    categorias: list[CategoriaDef]
    rendimiento: float
    rendimiento_source: str
    ficha: dict
    variables: dict[str, dict] = field(default_factory=dict)


def _texto(plantilla_json: dict, fuentes: dict[str, str]) -> str:
    return plantilla_json.format(**fuentes) if isinstance(plantilla_json, str) else ""


def _var(raw: dict, fuentes: dict[str, str]) -> Var:
    return Var(
        formulas=tuple(
            (f["formula"], tuple(f.get("requires") or ())) for f in raw.get("formulas") or []
        ),
        by=raw.get("by"),
        table={k: float(v) for k, v in (raw.get("table") or {}).items()},
        default=float(raw["default"]) if raw.get("default") is not None else None,
        source=_texto(raw.get("source", ""), fuentes),
    )


@lru_cache(maxsize=1)
def _catalogo() -> dict:
    raw = json.loads(
        resources.files("klave_engine.costing").joinpath("plantillas_matriz.json").read_text(
            encoding="utf-8"
        )
    )
    fuentes = raw.get("fuentes") or {}
    plantillas = []
    for p in raw["plantillas"]:
        match = p.get("match") or {}
        plantillas.append(Plantilla(
            key=p["key"], label=p["label"], units=tuple(p["units"]),
            match_all=tuple(match.get("all") or ()), match_any=tuple(match.get("any") or ()),
            match_not=tuple(match.get("not") or ()),
            vars={name: _var(v, fuentes) for name, v in (p.get("vars") or {}).items()},
            lines=tuple(
                Linea(
                    resource=line["resource"], formula=str(line["formula"]),
                    source=_texto(line.get("source", ""), fuentes),
                    by_fc=dict(line.get("by_fc") or {}),
                    by_material=dict(line.get("by_material") or {}),
                    when_any=tuple(line.get("when_any") or ()),
                    unless_any=tuple(line.get("unless_any") or ()),
                    materials=tuple(line.get("materials") or ()),
                    template=line.get("template"),
                    template_description=line.get("template_description"),
                )
                for line in p["lines"]
            ),
            rendimiento=Var(
                formulas=((p["rendimiento"]["formula"], ()),), by=None, table={}, default=None,
                source=_texto(p["rendimiento"].get("source", ""), fuentes),
            ),
            unit_scale={k: float(v) for k, v in (p.get("unit_scale") or {}).items()},
        ))
    cuadrillas = {
        code: CuadrillaDef(
            code=code, description=c["description"],
            members=tuple((m, float(q)) for m, q in c["members"].items()),
        )
        for code, c in (raw.get("cuadrillas") or {}).items()
    }
    insumos = {
        code: InsumoDef(code=code, description=i["description"], unit=i["unit"],
                        resource_type=i.get("resource_type", "material"))
        for code, i in (raw.get("insumos") or {}).items()
    }
    categorias = {
        code: CategoriaDef(code=code, description=c["description"],
                           salario_nominal=float(c["salario_nominal"]))
        for code, c in (raw.get("categorias") or {}).items()
    }
    return {"plantillas": plantillas, "cuadrillas": cuadrillas, "insumos": insumos,
            "categorias": categorias, "version": raw.get("version", "")}


def cargar_plantillas() -> list[Plantilla]:
    return list(_catalogo()["plantillas"])


def cuadrillas_definidas() -> dict[str, CuadrillaDef]:
    return dict(_catalogo()["cuadrillas"])


def categorias_definidas() -> dict[str, CategoriaDef]:
    return dict(_catalogo()["categorias"])


@lru_cache(maxsize=1)
def precios_semilla() -> dict:
    """Precios de referencia para insumos sin precio: vigencia, región, la
    marca «precio de referencia, validar» y el precio por clave."""
    raw = json.loads(
        resources.files("klave_engine.costing").joinpath("insumos_semilla.json").read_text(
            encoding="utf-8"
        )
    )
    return {
        "vigencia": raw.get("vigencia", ""), "region": raw.get("region", "MX"),
        "source": raw.get("source", "precio de referencia, validar"),
        "precios": {k: float(v) for k, v in (raw.get("precios") or {}).items()},
    }


def elegir_plantilla(description: str, unit: str, phase: str = "") -> Plantilla | None:
    """La primera plantilla cuya unidad y palabras coinciden; las específicas
    van antes que las genéricas en la tabla, así que «dala» gana a «concreto»."""
    low = normalize(description)
    key = unit_key(unit)
    for plantilla in _catalogo()["plantillas"]:
        if key not in {unit_key(u) for u in plantilla.units}:
            continue
        if any(word not in low for word in plantilla.match_all):
            continue
        if plantilla.match_any and not any(word in low for word in plantilla.match_any):
            continue
        if any(word in low for word in plantilla.match_not):
            continue
        return plantilla
    return None


def _resolver_var(name: str, var: Var, ficha: dict, resueltas: dict[str, float]) -> float:
    scope = {**ficha, **resueltas}
    for formula, requires in var.formulas:
        if all(scope.get(r) is not None for r in requires):
            try:
                return evaluar(formula, scope)
            except ValueError:
                continue
    if var.by:
        clave = ficha.get(var.by)
        if isinstance(clave, str) and clave in var.table:
            return var.table[clave]
    if var.default is not None:
        return var.default
    raise ValueError(f"La variable «{name}» no se puede resolver con esta ficha.")


def _linea_aplica(line: Linea, ficha: dict) -> bool:
    low = ficha.get("texto", "")
    if line.when_any and not any(w in low for w in line.when_any):
        return False
    if line.unless_any and any(w in low for w in line.unless_any):
        return False
    if line.materials and ficha.get("material") not in line.materials:
        return False
    return True


def _recurso(line: Linea, ficha: dict) -> tuple[str, InsumoDef | None]:
    """La clave del recurso de la línea: por f'c, por material o por plantilla
    de clave (tubo por material y diámetro), y su definición si es nuevo."""
    insumos = _catalogo()["insumos"]
    if line.template:
        if not ficha.get("diam_mm"):
            # Nadie publica el precio de un tubo sin decir de cuál: el
            # diámetro llega con la firma del plano o escrito en el concepto.
            raise ValueError(
                "La tubería necesita su diámetro para generar la matriz: el plano lo "
                "declara por línea o se escribe en el concepto («de 100 mm»)."
            )
        try:
            code = line.template.format(
                material=ficha.get("material") or "PVC-SAN",
                diam_mm=int(ficha["diam_mm"]),
            )
        except (KeyError, ValueError):
            code = line.resource
        if code in insumos:
            return code, insumos[code]
        descripcion = (line.template_description or code).format(
            material_label=ficha.get("material_label") or "PVC sanitario",
            diam_mm=int(ficha.get("diam_mm") or 0) or "?",
            material=ficha.get("material") or "",
        )
        return code, InsumoDef(
            code=code, description=descripcion, unit="M", resource_type="material",
        )
    if line.by_fc and ficha.get("fc") is not None:
        code = line.by_fc.get(str(int(ficha["fc"])), line.resource)
        return code, insumos.get(code)
    if line.by_material and ficha.get("material"):
        code = line.by_material.get(ficha["material"], line.resource)
        return code, insumos.get(code)
    return line.resource, insumos.get(line.resource)


def generar(
    description: str, unit: str, phase: str = "", spec_signature: dict | None = None
) -> Generada:
    """La matriz propuesta para un concepto: líneas con cantidad y fuente,
    las cuadrillas que usa (con sus miembros), los insumos que habría que
    dar de alta y el rendimiento. ValueError cuando ninguna plantilla
    reconoce el texto."""
    plantilla = elegir_plantilla(description, unit, phase)
    if plantilla is None:
        raise ValueError(
            f"Ninguna plantilla reconoce «{description[:60]}» por {unit}: "
            "captura la matriz a mano o tráela de la base."
        )
    ficha = ficha_numerica(description, spec_signature)
    resueltas: dict[str, float] = {}
    variables: dict[str, dict] = {}
    for name, var in plantilla.vars.items():
        resueltas[name] = _resolver_var(name, var, ficha, resueltas)
        variables[name] = {"valor": resueltas[name], "fuente": var.source}
    scale = plantilla.unit_scale.get(unit.upper(), 1.0) if plantilla.unit_scale else 1.0
    scope = {**ficha, **resueltas}
    catalogo = _catalogo()
    lines: list[LineaGenerada] = []
    insumos_nuevos: dict[str, InsumoDef] = {}
    cuadrillas: dict[str, CuadrillaDef] = {}
    for line in plantilla.lines:
        if not _linea_aplica(line, ficha):
            continue
        code, definicion = _recurso(line, ficha)
        quantity = evaluar(line.formula, scope)
        if code != "EQ-HERRAMIENTA":
            quantity *= scale
        if quantity <= 0:
            continue
        lines.append(LineaGenerada(
            resource_code=code, quantity=round(quantity, 6), source=line.source,
            formula=line.formula,
        ))
        if definicion is not None:
            insumos_nuevos[code] = definicion
        if code in catalogo["cuadrillas"]:
            cuadrillas[code] = catalogo["cuadrillas"][code]
    categorias = {
        member: catalogo["categorias"][member]
        for c in cuadrillas.values() for member, _ in c.members
        if member in catalogo["categorias"]
    }
    rendimiento = evaluar(plantilla.rendimiento.formulas[0][0], scope)
    if scale != 1.0:
        rendimiento /= scale
    return Generada(
        plantilla_key=plantilla.key, plantilla_label=plantilla.label, lines=lines,
        cuadrillas=list(cuadrillas.values()), insumos_nuevos=list(insumos_nuevos.values()),
        categorias=list(categorias.values()), rendimiento=round(rendimiento, 4),
        rendimiento_source=plantilla.rendimiento.source, ficha=ficha, variables=variables,
    )


def plantillas_resumen() -> list[dict]:
    """Las plantillas para enseñarlas: clave, familia, unidades, líneas con
    fórmula y fuente, variables con fuente."""
    return [
        {
            "key": p.key, "label": p.label, "units": list(p.units),
            "lines": [
                {"resource": line.resource, "formula": line.formula, "source": line.source}
                for line in p.lines
            ],
            "vars": {name: {"source": v.source, "default": v.default, "table": v.table}
                     for name, v in p.vars.items()},
            "rendimiento": {
                "formula": p.rendimiento.formulas[0][0], "source": p.rendimiento.source,
            },
        }
        for p in _catalogo()["plantillas"]
    ]
