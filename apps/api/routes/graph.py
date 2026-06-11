from fastapi import APIRouter, Depends

from apps.api.dependencies import ProjectStore, get_store

router = APIRouter(prefix="/projects")


@router.get("/{project_id}/graph")
def get_graph(
    project_id: str,
    include_elements: bool = True,
    store: ProjectStore = Depends(get_store),
) -> dict:
    graph = store.read_artifact(project_id, "drawing_graph.json")
    if not include_elements:
        return {
            "project_id": graph["project_id"],
            "node_count_by_type": graph["node_count_by_type"],
            "edge_count_by_type": graph["edge_count_by_type"],
        }
    return graph
