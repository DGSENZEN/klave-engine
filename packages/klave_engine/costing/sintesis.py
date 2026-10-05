"""Variantes del plano: un renglón del motor se separa en lo que el plano
especifica distinto.

El motor cuenta «Columnas y castillos de concreto armado» como un solo
renglón; el plano dice que hay K-1 de 15×15 con 4 #3 y C-2 de 30×40 con
8 #5, y un tabulador —o el catálogo del taller— las publica por separado
porque cuestan distinto. Aquí cada detección recibe su **firma** (los datos
que cambian el precio, por familia), los elementos se agrupan por firma, y
la cantidad de cada grupo sale de la misma regla que midió el renglón,
repartida para que las variantes sumen exactamente lo que el renglón dice.
Nada se inventa: lo que el plano no dice, la firma no lo trae.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable

from klave_engine.detection.results import Detection

_SECTION = re.compile(r"(\d{1,3}(?:\.\d)?)\s*[x×]\s*(\d{1,3}(?:\.\d)?)", re.IGNORECASE)
_REBAR = re.compile(r"^\s*(\d{1,2})\s*#\s*(\d{1,2})\s*$")


def _seccion(value: object) -> str:
    m = _SECTION.search(str(value or ""))
    if not m:
        return ""
    a, b = (float(m.group(1)), float(m.group(2)))
    a, b = sorted((a, b))
    return f"{a:g}x{b:g}"


def firma(detection: Detection, meters_factor: float) -> dict[str, str]:
    """Lo que el plano declara de este elemento y cambia su precio. Orden fijo
    de campos para que la misma especificación dé siempre la misma firma."""
    props = detection.properties or {}
    kind = detection.detection_type.value
    out: dict[str, str] = {}
    if kind in ("column_tag", "beam_tag"):
        seccion = _seccion(props.get("section_cm"))
        if seccion:
            out["seccion"] = seccion
        armado = str(props.get("spec_rebar") or "").replace(" ", "")
        if armado:
            out["armado"] = armado
    elif kind == "wall":
        tipo = str(props.get("wall_kind") or "")
        if tipo:
            out["tipo"] = tipo
        espesor = props.get("estimated_thickness")
        if espesor:
            cm = round(float(espesor) * meters_factor * 100)
            if 5 <= cm <= 80:
                out["espesor_cm"] = str(cm)
    elif kind == "slab_region":
        sistema = str(props.get("family") or "")
        if sistema:
            out["sistema"] = sistema
        if props.get("thickness_cm"):
            out["espesor_cm"] = f"{float(props['thickness_cm']):g}"
    elif kind == "footing":
        tipo = str(props.get("footing_kind") or "")
        if tipo:
            out["tipo"] = tipo
    elif kind == "pile":
        if props.get("diameter"):
            cm = round(float(props["diameter"]) * meters_factor * 100)
            if 20 <= cm <= 250:
                out["diametro_cm"] = str(cm)
    elif kind == "pipe_run":
        for campo in ("material", "diametro"):
            valor = str(props.get(campo) or "").strip()
            if valor:
                out[campo] = valor
    return out


# Conceptos cuyo precio no depende de la especificación de los elementos que
# los miden: el trazo se mide sobre la losa, el aplanado y la pintura sobre el
# muro, pero cuestan lo mismo sea la losa reticular o maciza, el muro de 15 o
# de 20. Separarlos sería ruido con cara de precisión.
SIN_VARIANTES = ("PRE-", "ACA-", "PIS-")

_MM = re.compile(r"(\d{1,4})\s*mm", re.IGNORECASE)


def separa(concept_code: str) -> bool:
    return not concept_code.startswith(SIN_VARIANTES)


def slug(signature: dict[str, str]) -> str:
    """La parte legible de la clave: «30X40-8N4», «BLOCK-15», «51MM», «GEN»."""
    if not signature:
        return "GEN"
    parts = []
    for campo, value in signature.items():
        if campo == "diametro" and (m := _MM.search(value)):
            parts.append(f"{m.group(1)}MM")
            continue
        token = re.sub(r"[^A-Z0-9]+", "", value.upper().replace("#", "N").replace("/", "-"))
        parts.append(token or "X")
    return "-".join(parts)[:40]


def variant_key(concept_code: str, signature: dict[str, str]) -> str:
    return f"{concept_code}.{slug(signature)}"


def _armado_frase(armado: str) -> str:
    m = _REBAR.match(armado)
    if m:
        return f"armado con {m.group(1)} vars. #{m.group(2)}"
    return f"armado {armado}"


def descripcion_variante(base: str, signature: dict[str, str]) -> str:
    """La descripción del renglón con la especificación dentro de su identidad
    (antes del «incluye»), en el idioma de un catálogo de licitación."""
    if not signature:
        return base
    low = base.lower()
    frases: list[str] = []
    if signature.get("seccion"):
        a, b = signature["seccion"].split("x")
        frases.append(f"de sección {a}×{b} cm")
    if signature.get("armado"):
        frases.append(_armado_frase(signature["armado"]))
    tipo = signature.get("tipo")
    if tipo and tipo.lower() not in low:
        frases.append(f"de {tipo}")
    sistema = signature.get("sistema")
    if sistema and sistema.lower() not in low:
        frases.append(f"{sistema}")
    if signature.get("espesor_cm") and "espesor" not in low:
        frases.append(f"de {signature['espesor_cm']} cm de espesor")
    if signature.get("diametro_cm") and "ø" not in low:
        frases.append(f"Ø{signature['diametro_cm']} cm")
    if signature.get("material") and signature["material"].lower() not in low:
        frases.append(f"de {signature['material']}")
    if signature.get("diametro") and signature["diametro"].lower() not in low:
        frases.append(f"de {signature['diametro']}")
    if not frases:
        return base
    from klave_engine.costing.boq import _con_especificacion

    return _con_especificacion(base, ", ".join(frases))


def agrupar(
    detections: Iterable[Detection], meters_factor: float
) -> list[tuple[dict[str, str], list[Detection]]]:
    """Las detecciones por firma, en el orden en que aparece cada una."""
    groups: dict[str, tuple[dict[str, str], list[Detection]]] = {}
    for d in detections:
        sig = firma(d, meters_factor)
        key = slug(sig)
        if key not in groups:
            groups[key] = (sig, [])
        groups[key][1].append(d)
    return list(groups.values())


def repartir(total: float, parts: list[float], digits: int = 6) -> list[float]:
    """Reparte ``total`` en proporción a ``parts`` y cuadra al último: la suma
    es exactamente ``total`` (a ``digits`` decimales)."""
    if not parts:
        return []
    base = sum(parts)
    if base <= 0:
        shares = [total / len(parts)] * len(parts)
    else:
        shares = [total * p / base for p in parts]
    rounded = [round(x, digits) for x in shares[:-1]]
    rounded.append(round(total - sum(rounded), digits))
    return rounded


def dividir(
    concept_code: str,
    base_description: str,
    total: float,
    matched: list[Detection],
    meters_factor: float,
    measure: Callable[[list[Detection]], tuple[float, list[Detection]]],
) -> tuple[list[dict], float]:
    """Las variantes de un renglón: cada grupo se mide con la misma regla
    (``measure`` devuelve cantidad y elementos que contribuyeron) y se
    reparte a ``total``. Devuelve las variantes y el factor de ajuste (1.0 si
    los grupos ya sumaban el renglón)."""
    groups = agrupar(matched, meters_factor)
    medidas = [measure(dets) for _sig, dets in groups]
    quantities = [q for q, _dets in medidas]
    suma = sum(quantities)
    factor = total / suma if suma > 0 else 1.0
    repartidas = repartir(total, quantities)
    variants: list[dict] = []
    for (sig, _dets), (_q, contributing), quantity in zip(
        groups, medidas, repartidas, strict=True
    ):
        if quantity <= 0 and not contributing:
            continue
        variants.append({
            "key": variant_key(concept_code, sig),
            "signature": sig,
            "description": descripcion_variante(base_description, sig),
            "quantity": quantity,
            "source_detection_count": len(contributing),
            "source_detections": [d.detection_id for d in contributing][:200],
        })
    return variants, factor
