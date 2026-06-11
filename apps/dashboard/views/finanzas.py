import plotly.graph_objects as go
import streamlit as st
from common import load_artifact, money, select_project_root


def render() -> None:
    st.title("Flujo Financiero")
    root = select_project_root()
    if root is None:
        return
    costs = load_artifact(root, "cost_report.json")
    if not costs:
        return
    plan = costs["financial"]
    periods = plan["periods"]

    col1, col2, col3 = st.columns(3)
    col1.metric(
        f"Anticipo ({plan['advance_payment_pct']:.0f}%)",
        money(plan["advance_payment"]),
    )
    col2.metric(
        f"Retenciones ({plan['retention_pct']:.0f}%)",
        money(plan["total_retention"]),
    )
    col3.metric("Operación anual (O&M)", money(plan["annual_operating_cost"]))

    if periods:
        figure = go.Figure()
        labels = [p["label"] for p in periods]
        figure.add_trace(
            go.Bar(x=labels, y=[p["billing"] for p in periods], name="Estimación")
        )
        figure.add_trace(
            go.Bar(
                x=labels,
                y=[-p["advance_amortization"] for p in periods],
                name="Amortización de anticipo",
            )
        )
        figure.add_trace(
            go.Bar(x=labels, y=[-p["retention"] for p in periods], name="Retención")
        )
        figure.add_trace(
            go.Scatter(
                x=labels,
                y=[p["net_cashflow"] for p in periods],
                name="Flujo neto",
                mode="lines+markers",
                line={"color": "#16a34a", "width": 3},
            )
        )
        figure.update_layout(
            barmode="relative", height=420,
            margin={"l": 10, "r": 10, "t": 30, "b": 10},
        )
        st.plotly_chart(figure, use_container_width=True, config={"displaylogo": False})

        st.dataframe(
            [
                {
                    "Periodo": p["label"],
                    "Gasto directo": p["direct_spend"],
                    "Estimación": p["billing"],
                    "Amortización": p["advance_amortization"],
                    "Retención": p["retention"],
                    "Flujo neto": p["net_cashflow"],
                    "Avance": f"{p['progress_pct']:.1f}%",
                }
                for p in periods
            ],
            use_container_width=True,
        )

    st.subheader("Proyección de operación y mantenimiento")
    projection = plan["operating_projection"]
    if projection:
        figure = go.Figure()
        figure.add_trace(
            go.Bar(
                x=[f"Año {y['year']}" for y in projection],
                y=[y["operation"] for y in projection],
                name="Operación",
            )
        )
        figure.add_trace(
            go.Bar(
                x=[f"Año {y['year']}" for y in projection],
                y=[y["maintenance"] for y in projection],
                name="Mantenimiento",
            )
        )
        figure.update_layout(
            barmode="stack", height=320,
            margin={"l": 10, "r": 10, "t": 30, "b": 10},
        )
        st.plotly_chart(figure, use_container_width=True, config={"displaylogo": False})
        st.caption(
            "Proyección basada en porcentajes anuales sobre el total con "
            "contingencia (configurables)."
        )
