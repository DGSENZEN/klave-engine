from fastapi import APIRouter, Depends, Query

from apps.api.dependencies import ProjectStore, get_store

router = APIRouter(prefix="/projects")


@router.get("/{project_id}/detections")
def get_detections(
    project_id: str,
    detection_type: str | None = None,
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
    store: ProjectStore = Depends(get_store),
) -> dict:
    detections = store.read_artifact(project_id, "detections.json")
    if detection_type is not None:
        detections = [d for d in detections if d["detection_type"] == detection_type]
    detections = [d for d in detections if d["confidence"] >= min_confidence]
    return {"total": len(detections), "detections": detections}
