"""Asociación de la lectura estructural: a qué pieza pertenece cada texto del plano."""

from klave_engine.dxf.entities import EntityType, NormalizedEntity


def ancla_texto(e: NormalizedEntity) -> tuple[float, float]:
    """El punto donde el dibujante puso el texto, no la esquina de su caja.

    Un TEXT con alineación distinta de «izquierda-base» se coloca por su punto
    de alineación (código 11): el ``insert`` de esos textos queda en otro lado.
    Si no hay alineación, el ancla es el ``insert``; sin él, la esquina inferior
    izquierda de la caja."""
    propiedades = e.properties
    if e.entity_type == EntityType.text and (
        propiedades.get("halign", 0) != 0 or propiedades.get("valign", 0) != 0
    ):
        punto = propiedades.get("align_point")
        if punto is not None:
            return (float(punto[0]), float(punto[1]))
    insercion = propiedades.get("insert")
    if insercion is not None:
        return (float(insercion[0]), float(insercion[1]))
    return (e.bbox[0], e.bbox[1])
