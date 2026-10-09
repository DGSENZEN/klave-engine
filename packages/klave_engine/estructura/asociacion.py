"""Asociación de la lectura estructural: a qué pieza pertenece cada texto del plano."""

from klave_engine.dxf.entities import EntityType, NormalizedEntity

# En «alineado» (3) y «ajustado» (5) el código 11 es donde TERMINA la línea base:
# el texto arranca en el ``insert``, así que ése es su ancla.
_HALIGN_CON_FINAL_EN_EL_PUNTO = (3, 5)


def ancla_texto(e: NormalizedEntity) -> tuple[float, float]:
    """El punto donde el dibujante puso el texto, no la esquina de su caja.

    Un TEXT con alineación distinta de «izquierda-base» se coloca por su punto
    de alineación (código 11): el ``insert`` de esos textos queda en otro lado.
    Excepto «alineado» y «ajustado», donde el código 11 es el final de la línea
    base y el ancla sigue siendo el ``insert``. Si no hay alineación, el ancla
    es el ``insert``; sin él, la esquina inferior izquierda de la caja."""
    propiedades = e.properties
    halign = propiedades.get("halign", 0)
    if (
        e.entity_type == EntityType.text
        and halign not in _HALIGN_CON_FINAL_EN_EL_PUNTO
        and (halign != 0 or propiedades.get("valign", 0) != 0)
    ):
        punto = propiedades.get("align_point")
        if punto is not None:
            return (float(punto[0]), float(punto[1]))
    insercion = propiedades.get("insert")
    if insercion is not None:
        return (float(insercion[0]), float(insercion[1]))
    return (e.bbox[0], e.bbox[1])
