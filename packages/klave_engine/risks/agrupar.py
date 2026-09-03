"""Riesgos se agrupa con la regla del Diagnóstico.

El principio 7 ya estaba escrito — «nunca un hallazgo por renglón»; seis
zapatas sin columna son UNA decisión — y `hallazgos.py` lo cumple desde su
nacimiento. Este paso salda la deuda M1 del otro sistema: los hallazgos que
las reglas emiten elemento por elemento se juntan en una tarjeta por tipo,
con su cuenta, su denominador cuando lo hay, y sus miembros completos (la
frase original de cada uno con su lugar en el plano, para que el salto al
visor no se pierda). La causa se ordena antes que el síntoma: un hallazgo
que explica a los demás abre la lista aunque su severidad sea baja.
"""

from __future__ import annotations

from collections import defaultdict

from klave_engine.risks.rules import RiskFinding, RiskMember

# Tipos que explican o invalidan a otros: van primero aunque sean «low»,
# porque leer 74 síntomas antes que su causa es leer al revés.
_CAUSAS = (
    "empty_drawing_after_parsing",
    "unknown_drawing_units",
    "sparse_grid",
    "unresolved_detail_reference",
)

# El título del oficio, nunca el nombre interno del método.
_TITULOS = {
    "sparse_grid": "Malla de ejes incompleta",
    "column_tag_without_grid": "Columnas sin eje cercano",
    "footing_without_column": "Zapatas sin columna etiquetada",
    "duplicate_column_tag": "Etiquetas de columna repetidas",
    "low_confidence_detection_in_takeoff": "Detecciones dudosas en la cuantificación",
    "unknown_drawing_units": "Unidades del plano sin determinar",
    "unknown_layer_entities": "Capas sin convención conocida",
    "empty_drawing_after_parsing": "Plano sin geometría legible",
    "unresolved_detail_reference": "Referencias a detalle sin resolver",
}

# La frase plural de la tarjeta; {n} elementos, {ejemplos} los primeros.
_PLURALES = {
    "column_tag_without_grid": "{n} columnas o castillos sin una intersección "
    "de ejes cerca (p. ej. {ejemplos}).",
    "footing_without_column": "{n} zapatas sin una columna etiquetada dentro "
    "del radio de búsqueda (p. ej. {ejemplos}).",
    "duplicate_column_tag": "{n} etiquetas de columna aparecen repetidas en "
    "lugares distantes (p. ej. {ejemplos}).",
    "low_confidence_detection_in_takeoff": "{n} de {total} detecciones de la "
    "cuantificación quedaron por debajo del umbral de confianza "
    "(p. ej. {ejemplos}).",
}

# Una acción por tarjeta, dicha una vez y en plural.
_ACCIONES = {
    "column_tag_without_grid": "Recorre estas columnas en el visor contra los "
    "ejes; si la malla está completa, varias pueden ser etiquetas de detalle.",
    "footing_without_column": "Recorre estas zapatas en el visor y revisa si "
    "soportan columnas sin etiqueta.",
    "duplicate_column_tag": "Confirma en el visor cuáles etiquetas se repiten "
    "a propósito y cuáles están mal puestas.",
    "low_confidence_detection_in_takeoff": "Recórrelas en el visor con las "
    "flechas y confirma o excluye cada una (C confirmar, X excluir).",
}

_SEVERIDAD_ORDEN = {"high": 0, "medium": 1, "low": 2}
_MAX_DETECCIONES = 200
_MAX_EJEMPLOS = 6


def _ejemplo(finding: RiskFinding) -> str:
    """La palabra que identifica al elemento: la etiqueta que su frase nombra."""
    for word in finding.message.split():
        limpio = word.strip(".,;:()«»")
        if limpio and any(c.isdigit() for c in limpio) and any(c.isalpha() for c in limpio):
            return limpio
    return ""


def agrupar_hallazgos(
    findings: list[RiskFinding], *, total_detecciones: int
) -> list[RiskFinding]:
    """Una tarjeta por tipo, con sus miembros; las causas abren la lista."""
    por_tipo: dict[str, list[RiskFinding]] = defaultdict(list)
    for finding in findings:
        por_tipo[finding.risk_type].append(finding)

    tarjetas: list[RiskFinding] = []
    for risk_type, grupo in por_tipo.items():
        titulo = _TITULOS.get(risk_type, "")
        if len(grupo) == 1:
            solo = grupo[0].model_copy(update={"titulo": titulo})
            tarjetas.append(solo)
            continue
        ejemplos = ", ".join(e for e in (_ejemplo(f) for f in grupo[:_MAX_EJEMPLOS]) if e)
        plantilla = _PLURALES.get(
            risk_type, "{n} hallazgos de este tipo (p. ej. {ejemplos})."
        )
        mensaje = plantilla.format(
            n=len(grupo), total=total_detecciones, ejemplos=ejemplos or "varios"
        )
        peor = min(grupo, key=lambda f: _SEVERIDAD_ORDEN[f.severity.value])
        detecciones: list[str] = []
        entidades: list[str] = []
        for f in grupo:
            detecciones.extend(f.related_detections)
            entidades.extend(f.source_entities)
        tarjetas.append(
            RiskFinding(
                risk_id=grupo[0].risk_id,
                risk_type=risk_type,
                severity=peor.severity,
                message=mensaje,
                source_entities=entidades[:_MAX_DETECCIONES],
                related_detections=detecciones[:_MAX_DETECCIONES],
                bbox=None,
                evidence=grupo[0].evidence,
                recommended_human_action=_ACCIONES.get(
                    risk_type, grupo[0].recommended_human_action
                ),
                titulo=titulo,
                member_count=len(grupo),
                members=[
                    RiskMember(
                        message=f.message,
                        bbox=f.bbox,
                        related_detections=f.related_detections[:5],
                    )
                    for f in grupo
                ],
            )
        )

    def _orden(card: RiskFinding) -> tuple:
        es_causa = card.risk_type in _CAUSAS
        return (
            0 if es_causa else 1,
            _CAUSAS.index(card.risk_type) if es_causa else 0,
            _SEVERIDAD_ORDEN[card.severity.value],
            -max(card.member_count, 1),
        )

    tarjetas.sort(key=_orden)
    return tarjetas
