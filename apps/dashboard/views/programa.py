from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from common import load_artifact, select_project_root


def render() -> None:
    st.title("Programa de Obra")
    root = select_project_root()
    if root is None:
        return
    costs = load_artifact(root, "cost_report.json")
    if not costs:
        return
    schedule = costs["schedule"]
    if not schedule["activities"]:
        st.info("No hay actividades programadas (presupuesto vacío).")
        return

    months = len(costs["financial"]["periods"])
    col1, col2, col3 = st.columns(3)
    col1.metric("Duración", f"{schedule['total_duration_days']} días hábiles")
    col2.metric("Meses estimados", months)
    col3.metric("Fases", " → ".join(schedule["phases"]))

    # Gantt: working days mapped onto a calendar starting today (7-day weeks
    # approximated; the schedule itself is in working days).
    start = date.today()
    rows = []
    for activity in schedule["activities"]:
        rows.append(
            {
                "Concepto": f"{activity['concept_code']} {activity['description'][:48]}",
                "Inicio": start + timedelta(days=activity["start_day"]),
                "Fin": start + timedelta(days=activity["end_day"]),
                "Fase": activity["phase"],
                "Días": activity["duration_days"],
            }
        )
    frame = pd.DataFrame(rows)
    figure = px.timeline(
        frame, x_start="Inicio", x_end="Fin", y="Concepto", color="Fase",
        hover_data=["Días"],
    )
    figure.update_yaxes(autorange="reversed")
    figure.update_layout(height=420, margin={"l": 10, "r": 10, "t": 30, "b": 10})
    st.plotly_chart(figure, use_container_width=True, config={"displaylogo": False})

    st.subheader("Curva S (avance financiero programado)")
    periods = costs["financial"]["periods"]
    s_curve = go.Figure()
    s_curve.add_trace(
        go.Bar(
            x=[p["label"] for p in periods],
            y=[p["billing"] for p in periods],
            name="Estimación mensual",
            marker_color="#93c5fd",
        )
    )
    s_curve.add_trace(
        go.Scatter(
            x=[p["label"] for p in periods],
            y=[p["accumulated_billing"] for p in periods],
            name="Acumulado",
            mode="lines+markers",
            line={"color": "#1d4ed8"},
            yaxis="y",
        )
    )
    s_curve.update_layout(height=380, margin={"l": 10, "r": 10, "t": 30, "b": 10})
    st.plotly_chart(s_curve, use_container_width=True, config={"displaylogo": False})

    st.subheader("Actividades")
    st.dataframe(
        [
            {
                "Clave": a["concept_code"],
                "Actividad": a["description"],
                "Fase": a["phase"],
                "Cantidad": f"{a['quantity']:,.2f} {a['unit']}",
                "Rendimiento": f"{a['rendimiento_per_day']:g} {a['unit']}/día",
                "Cuadrillas": a.get("crews", 1),
                "Duración (días)": a["duration_days"],
                "Inicio (día)": a["start_day"],
                "Fin (día)": a["end_day"],
                "Costo directo": a["direct_cost"],
            }
            for a in schedule["activities"]
        ],
        use_container_width=True,
    )
