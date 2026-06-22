import plotly.graph_objects as go
import streamlit as st
from common import DETECTION_LABELS_ES, load_artifact, select_project_root

KIND_LABELS = {"plan": "Planta (cuantificada)", "excluded": "Detalle/tabla (excluida)"}
KIND_COLORS = {"plan": "#2563eb", "excluded": "#9ca3af"}


def render() -> None:
    st.title("Vistas del Plano")
    st.caption(
        "Un plano empaqueta varias vistas (cimentación, niveles, azotea) más "
        "detalles y tablas. El motor atribuye cada detección a su vista para "
        "deduplicar elementos repetidos y excluir detalles del presupuesto."
    )
    root = select_project_root()
    if root is None:
        return
    seg = load_artifact(root, "views.json")
    if not seg:
        return

    if not seg["is_segmented"]:
        st.info(
            "Este plano se trata como una sola vista (no se detectaron ≥2 plantas "
            "etiquetadas). " + " ".join(seg.get("notes", []))
        )
        return

    levels = ", ".join(f"+{lvl:.2f}" for lvl in seg["npt_levels"]) or "no detectados"
    st.success(
        f"{len(seg['views'])} regiones detectadas — niveles N.P.T.: {levels}. "
        + " ".join(seg.get("notes", []))
    )

    st.dataframe(
        [
            {
                "Vista": v["title"],
                "Tipo": KIND_LABELS.get(v["kind"], v["kind"]),
                "Nivel": v.get("level_key") or "—",
                "N.P.T.": v.get("npt_level"),
                "Detecciones": sum(v["detection_counts"].values()),
                **{
                    DETECTION_LABELS_ES.get(k, k): n
                    for k, n in sorted(v["detection_counts"].items())
                },
            }
            for v in seg["views"]
        ],
        use_container_width=True,
    )

    # Spatial map of view regions (bbox rectangles colored by kind).
    figure = go.Figure()
    for v in seg["views"]:
        if not v.get("bbox"):
            continue
        x1, y1, x2, y2 = v["bbox"]
        figure.add_trace(
            go.Scatter(
                x=[x1, x2, x2, x1, x1],
                y=[y1, y1, y2, y2, y1],
                mode="lines",
                fill="toself",
                name=v["title"][:28],
                line={"color": KIND_COLORS.get(v["kind"], "#111827")},
                opacity=0.35,
            )
        )
    figure.update_layout(
        height=520, dragmode="pan", plot_bgcolor="white",
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
    )
    figure.update_xaxes(visible=False)
    figure.update_yaxes(visible=False, scaleanchor="x", scaleratio=1)
    st.plotly_chart(figure, use_container_width=True, config={"scrollZoom": True})
