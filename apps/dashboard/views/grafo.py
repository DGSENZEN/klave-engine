import plotly.graph_objects as go
import streamlit as st
from common import (
    DETECTION_COLORS,
    DETECTION_LABELS_ES,
    load_artifact,
    select_project_root,
)

SEMANTIC_TYPES = list(DETECTION_COLORS)


def render() -> None:
    st.title("Grafo del Plano")
    st.caption(
        "Nodos semánticos posicionados en el plano; las aristas muestran las "
        "relaciones que sustentan cada detección."
    )
    root = select_project_root()
    if root is None:
        return
    graph = load_artifact(root, "drawing_graph.json")
    if not graph:
        return

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Nodos por tipo")
        st.dataframe(
            [{"tipo": k, "cantidad": v} for k, v in graph["node_count_by_type"].items()],
            use_container_width=True,
        )
    with col2:
        st.subheader("Aristas por tipo")
        st.dataframe(
            [{"tipo": k, "cantidad": v} for k, v in graph["edge_count_by_type"].items()],
            use_container_width=True,
        )

    semantic = {
        n["node_id"]: n
        for n in graph["nodes"]
        if n["node_type"] in SEMANTIC_TYPES and n.get("bbox")
    }
    if not semantic:
        st.info("No hay nodos semánticos con posición para graficar.")
        return

    edge_types = sorted(
        {
            e["edge_type"]
            for e in graph["edges"]
            if e["source_node_id"] in semantic and e["target_node_id"] in semantic
        }
    )
    visible_edges = st.multiselect("Relaciones", edge_types, default=edge_types)

    figure = go.Figure()
    xs, ys = [], []
    for edge in graph["edges"]:
        if edge["edge_type"] not in visible_edges:
            continue
        a = semantic.get(edge["source_node_id"])
        b = semantic.get(edge["target_node_id"])
        if not a or not b:
            continue
        ax = (a["bbox"][0] + a["bbox"][2]) / 2
        ay = (a["bbox"][1] + a["bbox"][3]) / 2
        bx = (b["bbox"][0] + b["bbox"][2]) / 2
        by = (b["bbox"][1] + b["bbox"][3]) / 2
        xs += [ax, bx, None]
        ys += [ay, by, None]
    figure.add_trace(
        go.Scattergl(
            x=xs, y=ys, mode="lines", name="relaciones",
            line={"width": 0.6, "color": "#cbd5e1"}, hoverinfo="skip",
        )
    )

    for node_type in SEMANTIC_TYPES:
        nodes = [n for n in semantic.values() if n["node_type"] == node_type]
        if not nodes:
            continue
        figure.add_trace(
            go.Scattergl(
                x=[(n["bbox"][0] + n["bbox"][2]) / 2 for n in nodes],
                y=[(n["bbox"][1] + n["bbox"][3]) / 2 for n in nodes],
                mode="markers",
                name=DETECTION_LABELS_ES.get(node_type, node_type),
                marker={
                    "size": 7,
                    "color": DETECTION_COLORS[node_type],
                    "opacity": 0.85,
                },
                text=[f"{n['label']} ({n['confidence']:.2f})" for n in nodes],
                hoverinfo="text",
            )
        )
    figure.update_layout(
        height=680, dragmode="pan", plot_bgcolor="white",
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
    )
    figure.update_xaxes(visible=False)
    figure.update_yaxes(visible=False, scaleanchor="x", scaleratio=1)
    st.plotly_chart(
        figure, use_container_width=True,
        config={"scrollZoom": True, "displaylogo": False},
    )
