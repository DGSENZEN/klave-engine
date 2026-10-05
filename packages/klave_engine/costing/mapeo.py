"""El mapeo: cada variante del plano encuentra su concepto en el catálogo de
la oficina, y la oficina lo corrige una vez.

Una oficina no presupuesta con las claves del motor: tiene su catálogo —el que
importó de OPUS o Neodata, el que escribió a mano— con sus claves y sus
descripciones. Aquí la variante («Columnas de concreto armado f'c=250, de
sección 30×40 cm, armado con 8 vars. #5») se empareja con lo de la oficina
usando el mismo emparejador de siempre, con la ficha como compuerta:

- puntaje ≥ 0.8 → **automática**: se aplica y se dice por qué;
- 0.5 a 0.8 → **propuesta**: se muestra como duda, no se aplica hasta que
  alguien la confirme;
- debajo → **sin equivalente** en tu catálogo: la variante conserva su precio
  del motor (o se queda sin precio) y lo dice.

La memoria vive en el catálogo del taller (`variant_mappings`): una decisión
de una persona se respeta en el siguiente proyecto con la misma firma.
"""

from __future__ import annotations

from klave_engine.costing.catalog_store import CatalogStore
from klave_engine.costing.matching import Candidate, Match, rank
from klave_engine.costing.models import (
    BillOfQuantities,
    BoqLine,
    BoqVariant,
    UnitPriceAnalysis,
)

AUTOMATICA = 0.8
PROPUESTA = 0.5
APLICADOS = ("automatica", "confirmada")


def candidatos_del_taller(store: CatalogStore) -> list[Candidate]:
    """Lo que la oficina tiene: sus conceptos (los que no nacen de una regla
    del motor) y los renglones de las bases que importó con matrices."""
    candidates: list[Candidate] = []
    for row in store.load_concepts():
        # Ni las reglas del motor ni lo que Klave sembró o generó: el catálogo
        # de la oficina es lo que la oficina escribió, importó o adoptó.
        if row.get("rule_key") or (row.get("origin") or "taller") == "generada":
            continue
        candidates.append(Candidate(
            kind="concept", key=row["code"], clave=row["code"],
            description=row["description"], unit=row["unit"], price=None,
            source="tu catálogo", phase=row.get("phase") or "",
        ))
    keys = [s["source_key"] for s in store.list_sources() if s.get("kind") == "matrices"]
    if keys:
        for ref in store.list_reference_rows(keys):
            candidates.append(Candidate(
                kind="reference", key=str(ref["ref_id"]), clave=ref["clave"],
                description=ref["description"], unit=ref["unit"],
                price=float(ref["price"]) if ref.get("price") else None,
                source=ref.get("source_name") or "", phase=ref.get("group_description") or "",
            ))
    return candidates


def proponer(
    description: str, unit: str, phase: str, candidates: list[Candidate]
) -> tuple[str, Match | None]:
    matches = rank(description, unit, candidates, phase=phase, limit=1)
    if not matches or matches[0].score < PROPUESTA:
        return "sin_equivalente", None
    best = matches[0]
    return ("automatica" if best.score >= AUTOMATICA else "propuesta"), best


def _variantes(line: BoqLine) -> list[BoqVariant]:
    """Toda línea tiene al menos una variante: las derivadas (cimbra, acero,
    relleno) y las de levantamiento nacen sin firma."""
    if not line.variants:
        line.variants = [BoqVariant(
            key=f"{line.concept_code}.GEN", description=line.description,
            quantity=line.quantity, source_detection_count=line.source_detection_count,
            source_detections=list(line.source_detections),
        )]
    return line.variants


def _cuadrar(line: BoqLine) -> None:
    """Un ajuste manual, los pilotes vueltos metros o un paso derivado pudieron
    mover la cantidad del renglón: las variantes se reparten de nuevo para que
    sumen exactamente lo que el renglón dice."""
    from klave_engine.costing.sintesis import repartir

    variants = _variantes(line)
    current = sum(v.quantity for v in variants)
    if abs(current - line.quantity) <= 1e-6:
        return
    for variant, quantity in zip(
        variants, repartir(line.quantity, [v.quantity for v in variants]), strict=True
    ):
        variant.quantity = quantity
    if len(variants) > 1:
        line.assumptions.append(
            "Variantes repartidas en proporción tras un ajuste a la cantidad del renglón."
        )


def consolidar_variantes(
    boq: BillOfQuantities,
    mappings: dict[str, dict],
    apus: dict[str, UnitPriceAnalysis],
) -> None:
    """Aplica la memoria del mapeo a cada variante —clave y descripción de la
    oficina, precio de su concepto o de su renglón— y deja el importe del
    renglón como la suma de sus variantes."""
    for line in boq.lines:
        _cuadrar(line)
        line_price = None if line.unpriced else line.unit_price
        total = 0.0
        all_priced = True
        mapped_any = False
        for variant in line.variants:
            mapping = mappings.get(variant.key)
            variant.clave = ""
            variant.mapped_description = ""
            variant.mapping = ""
            variant.mapping_reason = ""
            price: float | None = line_price
            source = ""
            if mapping:
                variant.mapping = mapping["status"]
                variant.mapping_reason = mapping.get("reason") or ""
                if mapping["status"] in ("automatica", "propuesta", "confirmada"):
                    variant.clave = mapping.get("clave") or mapping.get("target_code") or ""
                    variant.mapped_description = mapping.get("description") or ""
                if mapping["status"] in APLICADOS:
                    mapped_any = True
                    if mapping.get("target_kind") == "concept":
                        apu = apus.get(mapping.get("target_code") or "")
                        if apu is not None:
                            price = apu.direct_unit_cost
                            source = f"matriz del taller · {mapping['target_code']}"
                    elif mapping.get("ref_price"):
                        price = float(mapping["ref_price"])
                        source = f"{mapping.get('ref_source') or 'tu base'} · {variant.clave}"
            variant.unit_price = price
            variant.price_source = source
            if price is None:
                variant.amount = None
                all_priced = False
            else:
                variant.amount = round(variant.quantity * price, 2)
                total += variant.amount
        if not mapped_any:
            continue  # sin decisiones de la oficina, el renglón queda como lo dejó el motor
        if all_priced:
            line.amount = round(total, 2)
            line.unit_price = round(total / line.quantity, 4) if line.quantity else 0.0
            line.unpriced = False
        else:
            line.unpriced = True
            line.amount = 0.0
        line.assumptions.append(
            "Precio por variante con los conceptos de tu catálogo a los que se mapearon."
        )
    boq.direct_cost_total = round(sum(line.amount for line in boq.lines), 2)
    totals: dict[str, float] = {}
    for line in boq.lines:
        totals[line.phase] = round(totals.get(line.phase, 0.0) + line.amount, 2)
    boq.totals_by_phase = totals


def mapear(
    boq: BillOfQuantities, store: CatalogStore, *, actor: str = "", rematch: bool = False
) -> dict:
    """Propone y guarda un destino para cada variante que todavía no tiene
    uno (o para todas las que no confirmó una persona, con ``rematch``)."""
    known = store.load_variant_mappings()
    candidates = candidatos_del_taller(store)
    counts = {"automatica": 0, "propuesta": 0, "sin_equivalente": 0, "conservadas": 0}
    if not candidates:
        return {**counts, "sin_catalogo": True}
    seen: set[str] = set()
    for line in boq.lines:
        for variant in _variantes(line):
            if variant.key in seen:
                continue
            seen.add(variant.key)
            existing = known.get(variant.key)
            if existing and (existing["status"] == "confirmada" or not rematch):
                counts["conservadas"] += 1
                continue
            pool = [
                c for c in candidates
                if not (c.kind == "concept" and c.key == line.concept_code)
            ]
            status, match = proponer(variant.description, line.unit, line.phase, pool)
            if match is None:
                store.set_variant_mapping(
                    variant.key, status="sin_equivalente",
                    reason="Ningún concepto de tu catálogo se parece lo suficiente.",
                    actor=actor,
                )
            else:
                c = match.candidate
                store.set_variant_mapping(
                    variant.key, status=status,
                    target_kind="concept" if c.kind == "concept" else "reference",
                    target_code=c.key if c.kind == "concept" else c.clave,
                    ref_id=int(c.key) if c.kind == "reference" else None,
                    clave=c.clave, description=c.description, unit=c.unit,
                    score=round(match.score, 3), reason="; ".join(match.reasons)[:300],
                    actor=actor,
                )
            counts[status] += 1
    return {**counts, "sin_catalogo": False}
