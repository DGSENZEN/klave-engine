"""Riesgos se agrupa con la regla del Diagnóstico: nunca un hallazgo por
renglón. Diecisiete zapatas sin columna son UNA tarjeta con su cuenta y sus
miembros; la causa se ordena antes que el síntoma; y la exposición por
severidad sigue contando elementos, no tarjetas."""

from klave_engine.graph.evidence import EvidencePacket
from klave_engine.risks.agrupar import agrupar_hallazgos
from klave_engine.risks.rules import RiskFinding, Severity


def _finding(risk_type, message, severity=Severity.medium, bbox=None, dets=None):
    return RiskFinding(
        risk_id=f"risk_{message[:8]}",
        risk_type=risk_type,
        severity=severity,
        message=message,
        related_detections=dets or [],
        bbox=bbox,
        evidence=EvidencePacket(
            source="obra", method="check", entity_ids=[], bbox=None,
            confidence=1.0, notes=[],
        ),
        recommended_human_action="Revísalo en el visor.",
    )


def test_un_tipo_repetido_es_una_tarjeta_con_cuenta_y_miembros():
    findings = [
        _finding("footing_without_column", f"La zapata F{i} no tiene columna.",
                 bbox=[float(i), 0.0, float(i) + 1.0, 1.0], dets=[f"det_{i}"])
        for i in range(17)
    ]
    grouped = agrupar_hallazgos(findings, total_detecciones=100)
    assert len(grouped) == 1
    card = grouped[0]
    assert card.member_count == 17
    assert "17" in card.message
    assert card.titulo and "footing" not in card.titulo  # sin nombres internos
    # Cada miembro conserva su frase y su bbox: el salto al visor sobrevive.
    assert len(card.members) == 17
    assert card.members[0].bbox == (0.0, 0.0, 1.0, 1.0)
    assert "F0" in card.members[0].message
    # Las detecciones ligadas se unen para el lote de revisión.
    assert len(card.related_detections) == 17


def test_el_singular_se_queda_como_esta():
    findings = [_finding("unknown_drawing_units", "Sin unidades.", Severity.high)]
    grouped = agrupar_hallazgos(findings, total_detecciones=10)
    assert len(grouped) == 1
    assert grouped[0].member_count in (0, 1)
    assert grouped[0].message == "Sin unidades."


def test_la_causa_va_antes_que_el_sintoma():
    findings = [
        *[_finding("footing_without_column", f"La zapata Z{i} no tiene columna.")
          for i in range(3)],
        _finding("sparse_grid", "Se leyeron 6 ejes; la comprobación no aplica.",
                 Severity.low),
    ]
    grouped = agrupar_hallazgos(findings, total_detecciones=50)
    # sparse_grid es low y aun así abre la lista: explica a los demás.
    assert grouped[0].risk_type == "sparse_grid"


def test_la_severidad_por_elementos_no_se_diluye():
    findings = [
        *[_finding("low_confidence_detection_in_takeoff", f"La detección D{i}.",
                   Severity.low) for i in range(5)],
        *[_finding("duplicate_column_tag", f"La etiqueta C-{i} se repite.",
                   Severity.medium) for i in range(2)],
    ]
    grouped = agrupar_hallazgos(findings, total_detecciones=40)
    assert len(grouped) == 2
    counts = {}
    for card in grouped:
        counts[card.severity.value] = counts.get(card.severity.value, 0) + max(
            card.member_count, 1
        )
    assert counts == {"low": 5, "medium": 2}
    # El denominador de la cuantificación viaja en la tarjeta de confianza.
    low = next(c for c in grouped if c.risk_type == "low_confidence_detection_in_takeoff")
    assert "5" in low.message and "40" in low.message
