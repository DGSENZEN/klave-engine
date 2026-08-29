"""El índice de prefabricados: las definiciones de bloque como ciudadanos.

Un plano de instalaciones se dibuja casi entero con bloques — el mueble, la
salida, la compuerta, el detalle típico. Detectar cada instancia desde cero
es repetir el mismo trabajo N veces y contar doble cuando el trazo interno
se cuela. Este índice clasifica **una vez por definición** — con la tabla
de símbolos, con la semántica del nombre (exportes tipo Revit) y con sus
ATTDEF — y estampa cada colocación. Las suites por disciplina lo consumen;
la Lectura lo enseña («qué datos jalan»)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from klave_engine.detection.dimensions import parse_block_name
from klave_engine.detection.instalaciones_symbols import familia_de_bloque
from klave_engine.detection.inventory import _ANNOTATION_BLOCK_RE
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.geometry.bbox import BBox


class PrefabInstance(BaseModel):
    entity_id: str
    source_file: str
    bbox: BBox


class PrefabDefinition(BaseModel):
    name: str
    familia: str | None = None  # lo que la tabla de símbolos reconoce
    que_es: str | None = None
    disciplina: str | None = None
    clase: str | None = None  # semántica del nombre (exportes tipo Revit)
    es_anotacion: bool = False  # cajetines, flechas de norte, simbología
    attdefs: list[str] = Field(default_factory=list)
    instances: list[PrefabInstance] = Field(default_factory=list)


def build_prefab_index(
    entities: list[NormalizedEntity], block_attdefs: dict[str, list[str]] | None = None
) -> list[PrefabDefinition]:
    """Una definición por nombre de bloque, con todas sus colocaciones.

    Los INSERT anidados también son colocaciones (el parser los conserva
    con su propio nombre); los bloques anónimos (``*X…``) nunca entran."""
    attdefs = block_attdefs or {}
    definitions: dict[str, PrefabDefinition] = {}
    for entity in entities:
        if entity.entity_type != EntityType.insert:
            continue
        name = (entity.block_name or "").strip()
        if not name or name.startswith("*"):
            continue
        definition = definitions.get(name)
        if definition is None:
            regla = familia_de_bloque(name, entity.layer or "")
            semantics = parse_block_name(name)
            definition = definitions[name] = PrefabDefinition(
                name=name,
                familia=regla.familia if regla else None,
                que_es=regla.que_es if regla else None,
                disciplina=regla.disciplina if regla else None,
                clase=getattr(semantics, "element_class", None),
                es_anotacion=bool(_ANNOTATION_BLOCK_RE.search(name)),
                attdefs=list(attdefs.get(name, [])),
            )
        definition.instances.append(
            PrefabInstance(
                entity_id=entity.entity_id,
                source_file=entity.source_file,
                bbox=entity.bbox,
            )
        )
    return sorted(definitions.values(), key=lambda d: (-len(d.instances), d.name))
