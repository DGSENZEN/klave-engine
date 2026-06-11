from fastapi import APIRouter, Depends, Query

from apps.api.dependencies import ProjectStore, get_store

router = APIRouter(prefix="/projects")


@router.get("/{project_id}/entities")
def get_entities(
    project_id: str,
    layer: str | None = None,
    entity_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=10000),
    offset: int = Query(default=0, ge=0),
    store: ProjectStore = Depends(get_store),
) -> dict:
    entities = store.read_artifact(project_id, "normalized_entities.json")
    if layer is not None:
        entities = [e for e in entities if e["layer"] == layer]
    if entity_type is not None:
        entities = [e for e in entities if e["entity_type"] == entity_type]
    return {
        "total": len(entities),
        "offset": offset,
        "limit": limit,
        "entities": entities[offset : offset + limit],
    }
