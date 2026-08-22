"""Counts become quantities only through a mapping the taller made.

A levantamiento says "16 × DESCSAN1" or "128 m on 00-SANITARIA". A mapping
says which concept of the catálogo that symbol or layer is, and how many
units each one is worth. Applied here, the mapped counts join the
presupuesto as lines with their provenance ("Levantamiento: …"); an
unmapped symbol stays a count, and a concept without a price never gets
a line.
"""

from klave_engine.costing.models import (
    BillOfQuantities,
    BoqLine,
    Concept,
    QuantityKind,
    UnitPriceAnalysis,
)


def _retotal(boq: BillOfQuantities) -> None:
    boq.direct_cost_total = round(sum(line.amount for line in boq.lines), 2)
    totals: dict[str, float] = {}
    for line in boq.lines:
        totals[line.phase] = round(totals.get(line.phase, 0.0) + line.amount, 2)
    boq.totals_by_phase = totals


def apply_inventory(
    boq: BillOfQuantities,
    catalog: list[Concept],
    apus: dict[str, UnitPriceAnalysis],
    inventory: dict | None,
    mappings: list[dict] | None,
) -> int:
    """Add (or extend) presupuesto lines from mapped symbols and layers.
    Returns how many mappings produced a quantity."""
    if not inventory or not mappings:
        return 0
    concepts = {concept.code: concept for concept in catalog}
    lines = {line.concept_code: line for line in boq.lines}
    applied = 0
    unit_label = inventory.get("unit")
    for mapping in mappings:
        kind = mapping.get("kind")
        pattern = str(mapping.get("pattern") or "").strip().lower()
        code = str(mapping.get("concept_code") or "")
        factor = float(mapping.get("factor") or 1.0)
        concept = concepts.get(code)
        if concept is None or not pattern:
            boq.warnings.append(
                f"Levantamiento: la asignación «{mapping.get('pattern')}» → {code} apunta a un "
                "concepto inexistente; se ignora."
            )
            continue
        total = 0.0
        hits = 0
        by_view: dict[str, float] = {}
        sheets_hit: list[str] = []
        for sheet in inventory.get("sheets") or []:
            if kind == "block":
                for block in sheet.get("blocks") or []:
                    if str(block.get("block_name", "")).lower() != pattern:
                        continue
                    total += float(block.get("count") or 0)
                    hits += int(block.get("count") or 0)
                    sheets_hit.append(sheet.get("label") or sheet.get("sheet", ""))
                    for view, n in (block.get("by_view") or {}).items():
                        by_view[view] = by_view.get(view, 0.0) + float(n)
            else:
                for run in sheet.get("runs") or []:
                    if str(run.get("layer", "")).lower() != pattern:
                        continue
                    if run.get("length_m") is None:
                        boq.warnings.append(
                            f"Levantamiento: la capa «{run.get('layer')}» no tiene longitud en "
                            "metros (unidad del dibujo desconocida); no se cuantifica."
                        )
                        continue
                    total += float(run["length_m"])
                    hits += int(run.get("segments") or 0)
                    sheets_hit.append(sheet.get("label") or sheet.get("sheet", ""))
                    for view, n in (run.get("by_view") or {}).items():
                        by_view[view] = by_view.get(view, 0.0) + float(n)
        if total <= 0:
            continue
        apu = apus.get(code)
        if apu is None:
            boq.warnings.append(
                f"Levantamiento: {code} ({concept.description[:40]}…) no tiene matriz ni precio "
                f"adoptado; {total:,.2f} de «{mapping.get('pattern')}» quedan sin costo."
            )
            continue
        quantity = round(total * factor, 4)
        what = "símbolos" if kind == "block" else ("m" if unit_label else "unidades de dibujo")
        note = (
            f"Levantamiento: {total:,.2f} {what} «{mapping.get('pattern')}» en "
            f"{', '.join(sorted(set(s for s in sheets_hit if s))[:3])}"
            + (f" × {factor:g} {concept.unit}" if factor != 1.0 else "")
        )
        split = {k: round(v * factor, 4) for k, v in by_view.items()} if len(by_view) > 1 else {}
        line = lines.get(code)
        if line is None:
            line = BoqLine(
                concept_code=code,
                description=concept.description,
                unit=concept.unit,
                quantity=quantity,
                unit_price=apu.direct_unit_cost,
                amount=round(quantity * apu.direct_unit_cost, 2),
                phase=concept.phase,
                raw_quantity=round(total, 4),
                raw_kind=QuantityKind.COUNT if kind == "block" else QuantityKind.LENGTH,
                source_detection_count=hits,
                confidence=0.8,
                assumptions=[note],
                by_view=split,
            )
            boq.lines.append(line)
            lines[code] = line
        else:
            line.quantity = round(line.quantity + quantity, 4)
            line.amount = round(line.quantity * line.unit_price, 2)
            line.assumptions.append(note)
            for view, n in split.items():
                line.by_view[view] = round(line.by_view.get(view, 0.0) + n, 4)
        applied += 1
    if applied:
        _retotal(boq)
    return applied
