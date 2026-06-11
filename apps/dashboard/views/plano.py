import streamlit as st
from common import (
    DETECTION_LABELS_ES,
    drawing_figure,
    load_artifact,
    select_project_root,
)


def render() -> None:
    st.title("Visor del Plano")
    root = select_project_root()
    if root is None:
        return
    entities = load_artifact(root, "normalized_entities.json")
    detections = load_artifact(root, "detections.json") or []
    if not entities:
        return

    layer_counts: dict[str, int] = {}
    for entity in entities:
        layer_counts[entity["layer"]] = layer_counts.get(entity["layer"], 0) + 1
    ordered_layers = sorted(layer_counts, key=layer_counts.get, reverse=True)

    with st.sidebar:
        st.subheader("Capas")
        default_layers = ordered_layers[:12]
        visible_layers = st.multiselect(
            "Capas visibles", ordered_layers, default=default_layers,
            format_func=lambda layer: f"{layer} ({layer_counts[layer]})",
        )
        st.subheader("Detecciones")
        available_types = sorted({d["detection_type"] for d in detections})
        visible_types = st.multiselect(
            "Tipos visibles",
            available_types,
            default=available_types,
            format_func=lambda t: DETECTION_LABELS_ES.get(t, t),
        )
        min_confidence = st.slider("Confianza mínima", 0.0, 1.0, 0.0, 0.05)

    filtered = [
        d
        for d in detections
        if d["detection_type"] in set(visible_types)
        and d["confidence"] >= min_confidence
    ]
    st.caption(
        f"{len(filtered):,} detecciones visibles de {len(detections):,} — "
        "usa la rueda del ratón para acercar y arrastra para desplazarte"
    )
    figure = drawing_figure(entities, set(visible_layers), filtered, set(visible_types))
    st.plotly_chart(
        figure,
        use_container_width=True,
        config={"scrollZoom": True, "displaylogo": False},
    )
