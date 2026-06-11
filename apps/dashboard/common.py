"""Shared dashboard helpers: cached artifact loading and plotly figure builders.

The dashboard contains no business logic; it renders processed JSON artifacts.
"""

import json
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

DETECTION_COLORS = {
    "grid_line": "#94a3b8",
    "grid_intersection": "#64748b",
    "column_tag": "#dc2626",
    "beam_tag": "#2563eb",
    "footing": "#b45309",
    "slab_region": "#059669",
    "wall": "#7c3aed",
    "detail_reference": "#db2777",
}

DETECTION_LABELS_ES = {
    "grid_line": "Ejes",
    "grid_intersection": "Intersecciones de ejes",
    "column_tag": "Columnas/castillos",
    "beam_tag": "Trabes",
    "footing": "Zapatas/dados",
    "slab_region": "Losas",
    "wall": "Muros",
    "detail_reference": "Referencias de detalle",
}


def select_project_root() -> Path | None:
    default = st.session_state.get("project_root", "data/raw/estructural_l04")
    value = st.sidebar.text_input("Carpeta del proyecto", value=default)
    st.session_state["project_root"] = value
    root = Path(value)
    if not root.is_dir():
        st.sidebar.warning(f"No existe la carpeta: {root}")
        return None
    return root


@st.cache_data(show_spinner=False)
def _read_json(path_str: str, mtime: float):
    return json.loads(Path(path_str).read_text(encoding="utf-8"))


def load_artifact(project_root: Path, name: str):
    path = project_root / "processed" / name
    if not path.exists():
        st.info(
            f"No se encontró `{name}`. Procesa el proyecto primero "
            "(`klave process <carpeta>` o POST /process)."
        )
        return None
    return _read_json(str(path), path.stat().st_mtime)


def money(value: float, currency: str = "MXN") -> str:
    return f"${value:,.2f} {currency}"


# ------------------------------------------------------------- drawing figure


def _segments_by_layer(entities: list[dict], layers: set[str]) -> dict[str, tuple]:
    """Per-layer x/y arrays with None separators, ready for one scattergl trace."""
    by_layer: dict[str, tuple[list, list]] = {}
    for entity in entities:
        layer = entity["layer"]
        if layer not in layers:
            continue
        xs, ys = by_layer.setdefault(layer, ([], []))
        points = entity.get("points")
        entity_type = entity["entity_type"]
        if points and len(points) >= 2:
            path = list(points)
            if entity.get("properties", {}).get("closed") and len(points) >= 3:
                path = path + [points[0]]
            for x, y in path:
                xs.append(x)
                ys.append(y)
            xs.append(None)
            ys.append(None)
        elif entity_type in ("circle", "arc"):
            x1, y1, x2, y2 = entity["bbox"]
            # approximate with the bbox outline
            for x, y in [(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)]:
                xs.append(x)
                ys.append(y)
            xs.append(None)
            ys.append(None)
    return by_layer


def drawing_figure(
    entities: list[dict],
    visible_layers: set[str],
    detections: list[dict] | None = None,
    visible_types: set[str] | None = None,
    height: int = 720,
) -> go.Figure:
    fig = go.Figure()
    for layer, (xs, ys) in sorted(_segments_by_layer(entities, visible_layers).items()):
        fig.add_trace(
            go.Scattergl(
                x=xs,
                y=ys,
                mode="lines",
                name=layer,
                line={"width": 0.7, "color": "#9ca3af"},
                hoverinfo="skip",
                legendgroup="capas",
                legendgrouptitle_text="Capas",
            )
        )

    if detections:
        visible_types = visible_types or set(DETECTION_COLORS)
        by_type: dict[str, tuple[list, list, list, list, list]] = {}
        for detection in detections:
            dtype = detection["detection_type"]
            if dtype not in visible_types:
                continue
            xs, ys, cx, cy, labels = by_type.setdefault(dtype, ([], [], [], [], []))
            x1, y1, x2, y2 = detection["bbox"]
            for x, y in [(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)]:
                xs.append(x)
                ys.append(y)
            xs.append(None)
            ys.append(None)
            cx.append((x1 + x2) / 2)
            cy.append((y1 + y2) / 2)
            labels.append(
                f"{detection['label']} ({detection['confidence']:.2f})"
            )
        for dtype, (xs, ys, cx, cy, labels) in sorted(by_type.items()):
            color = DETECTION_COLORS.get(dtype, "#111827")
            display = DETECTION_LABELS_ES.get(dtype, dtype)
            fig.add_trace(
                go.Scattergl(
                    x=xs, y=ys, mode="lines", name=display,
                    line={"width": 1.6, "color": color},
                    hoverinfo="skip",
                    legendgroup="detecciones",
                    legendgrouptitle_text="Detecciones",
                )
            )
            fig.add_trace(
                go.Scattergl(
                    x=cx, y=cy, mode="markers", showlegend=False,
                    marker={"size": 5, "color": color},
                    text=labels, hoverinfo="text",
                    legendgroup="detecciones",
                )
            )

    fig.update_layout(
        height=height,
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
        dragmode="pan",
        plot_bgcolor="white",
        legend={"orientation": "v", "x": 1.01},
    )
    fig.update_xaxes(showgrid=False, zeroline=False, visible=False)
    fig.update_yaxes(
        showgrid=False, zeroline=False, visible=False, scaleanchor="x", scaleratio=1
    )
    return fig
