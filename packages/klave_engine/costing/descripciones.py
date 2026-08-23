"""Descripciones largas al estilo LOPSRM: the paragraph every concept needs
on a catálogo de licitación, written from what the concept actually is
(its description, its specs, its matrix) instead of typed by hand.

The form is the customary one: «Suministro y colocación de …, incluye:
materiales, mano de obra, herramienta, equipo, …, limpieza y todo lo
necesario para su correcta ejecución. P.U.O.T.». Each clause is derived —
the verb from the unit and family, the "incluye" from the matrix's
resource types and named materials — so the text states nothing the
presupuesto does not price. A proposal to edit, marked as generated.
"""

from __future__ import annotations

import re

from klave_engine.costing.models import Concept, ResourceType, UnitPriceAnalysis

_EXECUTION_VERBS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"excavaci[oó]n|corte|despalme", re.I), "Ejecución de"),
    (re.compile(r"relleno|terrapl[eé]n|compactad", re.I), "Formación y compactación de"),
    (re.compile(r"acarreo|flete", re.I), "Acarreo de"),
    (re.compile(r"trazo|nivelaci[oó]n", re.I), "Trazo y nivelación de"),
    (re.compile(r"cimbra", re.I), "Cimbra y descimbra en"),
    (re.compile(r"\bacero\b|\bmalla\b|\barmex\b", re.I), "Suministro, habilitado y colocación de"),
    (re.compile(r"muro de concreto", re.I), "Suministro, fabricación y colocación de"),
    (re.compile(r"muros? de block|block|tabique|ladrillo", re.I), "Suministro y construcción de"),
    (re.compile(r"concreto|losa|castillo|columna|trabe|dala|zapata|firme", re.I),
     "Suministro, fabricación y colocación de"),
    (re.compile(r"aplanado|pintura|plaf[oó]n|piso|impermeab", re.I), "Suministro y aplicación de"),
    (re.compile(r"muro", re.I), "Suministro y construcción de"),
]
_MATERIAL_STOP = re.compile(r"\((referencia|calculado|cotizaci[oó]n)[^)]*\)", re.I)


_SUPPLIED = re.compile(r"^(cimbra|acero|malla|aplanado|pintura|piso|muro|block|tabique)", re.I)


_CIMBRA_HEAD = re.compile(
    r"^cimbra\s*(com[uú]n|de contacto|aparente|acabado aparente)?\s*(en|para|de)?\s*", re.I
)


def _verb_and_base(description: str) -> tuple[str, str]:
    """The verb for the work and the description it applies to; a
    description that already names the work ("Trazo y nivelación del
    terreno", "Cimbra en trabes") is not repeated after the verb."""
    base = description
    for pattern, verb in _EXECUTION_VERBS:
        match = pattern.search(description)
        if match is None:
            continue
        if match.start() == 0 and verb.lower().startswith(match.group(0).lower()):
            if verb.startswith("Cimbra"):
                return verb, _CIMBRA_HEAD.sub("", description, count=1) or description
            supplied = _SUPPLIED.match(description) is not None
            return ("Suministro y colocación de" if supplied else "Ejecución de"), base
        return verb, base
    return "Suministro y colocación de", base


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text else text


def long_description(concept: Concept, apu: UnitPriceAnalysis | None) -> str:
    verb, base = _verb_and_base(concept.description.strip().rstrip("."))
    parts = [f"{verb} {_lower_first(base)}"]
    includes: list[str] = []
    materials: list[str] = []
    has_labor = has_equipment = has_tool = False
    if apu is not None and apu.lines:
        for line in apu.lines:
            rtype = str(line.resource_type)
            if rtype in (ResourceType.material.value, "material"):
                name = _MATERIAL_STOP.sub("", line.description).strip(" ,")
                if name and name.lower() not in (m.lower() for m in materials):
                    materials.append(name)
            elif rtype in (ResourceType.labor.value, "mano_de_obra"):
                has_labor = True
            elif rtype in (ResourceType.equipment.value, "equipo"):
                if "herramienta" in line.description.lower():
                    has_tool = True
                else:
                    has_equipment = True
    if materials:
        includes.append("materiales (" + ", ".join(materials[:6]) + ")")
    else:
        includes.append("materiales")
    if has_labor or apu is None or not apu.lines:
        includes.append("mano de obra")
    if has_equipment:
        includes.append("equipo")
    if has_tool or apu is None or not apu.lines:
        includes.append("herramienta")
    includes.extend(["desperdicios", "acarreos dentro de la obra", "limpieza"])
    parts.append("incluye: " + ", ".join(includes))
    parts.append("y todo lo necesario para su correcta ejecución")
    text = ", ".join(parts[:2]) + " " + parts[2] + ". P.U.O.T."
    if apu is not None and apu.price_source and not apu.lines:
        text += f" (P.U. adoptado de {apu.price_source})."
    return text[:1].upper() + text[1:]


def unit_words(unit: str) -> str:
    return {
        "M2": "metro cuadrado", "M3": "metro cúbico", "M": "metro lineal", "KG": "kilogramo",
        "PZA": "pieza", "SAL": "salida", "TON": "tonelada", "LOTE": "lote", "JOR": "jornada",
    }.get(unit.upper(), unit)
