"""Pilotes in metres.

The planta counts the piles (CIM-010, one per mark); the metres come from the
length the plano declares — in the notes ("PILOTES DE 12 M"), in the cuadro
or from the AI reading of the sheet — never from a guess. With a length,
the count becomes a priced line in M (CIM-011) and the count line retires;
without one, the count stays on the presupuesto unpriced, visible, with the
question it raises.
"""

from __future__ import annotations

from klave_engine.costing.models import BillOfQuantities, BoqLine, QuantityKind
from klave_engine.detection.results import Detection

CODE_COUNT = "CIM-010"
CODE_METERS = "CIM-011"
PILE_FAMILY = "pilote"


def _declared_length(mark: str, specs: dict | None) -> float | None:
    """Length for one pile: its own spec, the family spec, or the sheet note."""
    if not specs:
        return None
    own = (specs.get("by_mark") or {}).get(mark.strip().upper()) or {}
    if own.get("length_m"):
        return float(own["length_m"])
    family = (specs.get("by_family") or {}).get(PILE_FAMILY) or {}
    if family.get("length_m"):
        return float(family["length_m"])
    if specs.get("pile_length_m"):
        return float(specs["pile_length_m"])
    return None


def apply_piles(
    boq: BillOfQuantities,
    catalog: list,
    apus: dict,
    detections: list[Detection],
    specs: dict | None,
) -> int:
    """Turn the pile count into metres when the plano says how long they are.
    Returns the number of piles with a length."""
    count_line = next((ln for ln in boq.lines if ln.concept_code == CODE_COUNT), None)
    if count_line is None or not count_line.source_detections:
        return 0
    by_id = {d.detection_id: d for d in detections}
    meters = 0.0
    lengths: dict[str, int] = {}
    with_length = 0
    missing: list[str] = []
    for det_id in count_line.source_detections:
        det = by_id.get(det_id)
        mark = det.label if det else det_id
        length = _declared_length(mark, specs)
        if length is None:
            missing.append(mark)
            continue
        meters += length
        with_length += 1
        lengths[f"{length:g} m"] = lengths.get(f"{length:g} m", 0) + 1
    if with_length == 0:
        count_line.assumptions.append(
            f"{len(count_line.source_detections)} pilotes sin longitud declarada: el plano no "
            "la trae en notas ni cuadro. Captúrala (lectura con IA o nota) para cuantificar "
            "en metros; mientras, la línea no tiene precio."
        )
        return 0
    concept = next((c for c in catalog if c.code == CODE_METERS), None)
    apu = apus.get(CODE_METERS)
    if concept is None:
        boq.warnings.append(
            f"Pilotes con longitud ({meters:,.1f} m) pero el catálogo no tiene el concepto "
            f"{CODE_METERS}."
        )
        return with_length
    notes = [
        f"{with_length} pilotes × longitud declarada ("
        + ", ".join(f"{n} de {length}" for length, n in sorted(lengths.items()))
        + ")"
    ]
    if missing:
        notes.append(
            f"{len(missing)} pilotes sin longitud declarada, no cuantificados en metros: "
            + ", ".join(sorted(set(missing))[:8])
        )
    unit_price = apu.direct_unit_cost if apu else 0.0
    boq.lines.append(
        BoqLine(
            concept_code=CODE_METERS,
            description=concept.description,
            unit=concept.unit,
            quantity=round(meters, 2),
            unit_price=unit_price,
            amount=round(meters * unit_price, 2),
            unpriced=apu is None,
            phase=concept.phase,
            raw_quantity=round(meters, 3),
            raw_kind=QuantityKind.LENGTH,
            source_detection_count=with_length,
            source_detections=list(count_line.source_detections)[:200],
            confidence=count_line.confidence,
            assumptions=list(concept.assumptions) + notes,
        )
    )
    if not missing:
        # Every pile is in metres now: the count line would double the story.
        boq.lines.remove(count_line)
    boq.direct_cost_total = round(sum(line.amount for line in boq.lines), 2)
    totals: dict[str, float] = {}
    for line in boq.lines:
        totals[line.phase] = round(totals.get(line.phase, 0.0) + line.amount, 2)
    boq.totals_by_phase = totals
    return with_length
