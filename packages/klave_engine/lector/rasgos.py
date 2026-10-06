"""Los rasgos que el modelo mira: sólo geometría y contexto.

S0 midió que los nombres de capa y de bloque no cruzan de una oficina a otra
(en un plano no visto rinden lo mismo que adivinar), así que viven en el
perfil del taller y el modelo compartido se queda con la forma. Las mismas
llaves salen de una detección (``detection.features``) y de un candidato
(``detection.candidates``)."""

from __future__ import annotations

NOMBRES = ("ancho_m", "alto_m", "proporcion", "area_m2", "dist_eje_m", "repeticion_bloque")


def _num(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def vector(features: dict) -> list[float | None]:
    ancho, alto = _num(features.get("ancho_m")), _num(features.get("alto_m"))
    area = ancho * alto if ancho is not None and alto is not None else None
    return [
        ancho, alto, _num(features.get("proporcion")), area,
        _num(features.get("dist_eje_m")), _num(features.get("repeticion_bloque")),
    ]


def en_ventana(features: dict) -> bool:
    """El tamaño que tiene un candidato: lo que cae fuera nunca se propone."""
    ancho, alto = _num(features.get("ancho_m")), _num(features.get("alto_m"))
    return bool(ancho and alto and min(ancho, alto) >= 0.08 and max(ancho, alto) <= 3.0)
