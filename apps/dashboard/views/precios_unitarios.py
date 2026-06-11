import plotly.graph_objects as go
import streamlit as st
from common import load_artifact, money, select_project_root

TYPE_LABELS = {"material": "Materiales", "mano_de_obra": "Mano de obra", "equipo": "Equipo"}


def render() -> None:
    st.title("Análisis de Precios Unitarios")
    root = select_project_root()
    if root is None:
        return
    costs = load_artifact(root, "cost_report.json")
    if not costs:
        return
    apus = costs["apus"]
    if not apus:
        st.info("No hay análisis de precios unitarios generados.")
        return

    selected = st.selectbox(
        "Concepto",
        apus,
        format_func=lambda apu: f"{apu['concept_code']} — {apu['concept_description']}",
    )
    st.metric(
        f"Costo directo por {selected['unit']}",
        money(selected["direct_unit_cost"]),
    )

    st.dataframe(
        [
            {
                "Insumo": line["resource_code"],
                "Descripción": line["description"],
                "Unidad": line["unit"],
                "Cantidad": line["quantity"],
                "Costo unitario": line["unit_cost"],
                "Importe": line["amount"],
                "Tipo": TYPE_LABELS.get(line["resource_type"], line["resource_type"]),
            }
            for line in selected["lines"]
        ],
        use_container_width=True,
    )

    breakdown = {
        TYPE_LABELS.get(k, k): v for k, v in selected["breakdown"].items() if v > 0
    }
    figure = go.Figure(
        go.Pie(labels=list(breakdown), values=list(breakdown.values()), hole=0.45)
    )
    figure.update_layout(height=360, margin={"l": 10, "r": 10, "t": 10, "b": 10})
    st.plotly_chart(figure, use_container_width=True, config={"displaylogo": False})
    st.caption(
        "Precios de insumos de referencia (MXN); sustituir por cotizaciones "
        "vigentes del proyecto."
    )
