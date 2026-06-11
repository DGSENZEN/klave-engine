import plotly.graph_objects as go
import streamlit as st
from common import load_artifact, money, select_project_root


def render() -> None:
    st.title("Integración de Costos")
    root = select_project_root()
    if root is None:
        return
    costs = load_artifact(root, "cost_report.json")
    if not costs:
        return
    integration = costs["integration"]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Costo directo", money(integration["direct_cost"]))
    col2.metric("Precio de venta", money(integration["sale_price"]))
    col3.metric("Contingencia", money(integration["contingency"]))
    col4.metric("Total", money(integration["grand_total"]))
    st.caption(f"Factor de sobrecosto: {integration['overcost_factor']:.4f}")

    labels = ["Costo directo"]
    values = [integration["direct_cost"]]
    measures = ["absolute"]
    for line in integration["lines"]:
        labels.append(f"{line['description']} ({line['percentage']}%)")
        values.append(line["amount"])
        measures.append("relative")
    labels.append("Precio de venta")
    values.append(integration["sale_price"])
    measures.append("total")
    labels.append("Contingencia")
    values.append(integration["contingency"])
    measures.append("relative")
    labels.append("Total con contingencia")
    values.append(integration["grand_total"])
    measures.append("total")

    figure = go.Figure(
        go.Waterfall(
            x=labels,
            y=values,
            measure=measures,
            connector={"line": {"color": "#cbd5e1"}},
        )
    )
    figure.update_layout(height=480, margin={"l": 10, "r": 10, "t": 30, "b": 10})
    st.plotly_chart(figure, use_container_width=True, config={"displaylogo": False})

    st.subheader("Desglose")
    rows = [
        {
            "Componente": line["description"],
            "Base": money(line["base"]),
            "%": line["percentage"],
            "Importe": money(line["amount"]),
            "Acumulado": money(line["accumulated"]),
        }
        for line in integration["lines"]
    ]
    st.dataframe(rows, use_container_width=True)
    st.caption(
        "Secuencia de integración: CD → indirectos → financiamiento → utilidad → "
        "cargos adicionales = precio de venta; la contingencia se calcula sobre "
        "el precio de venta. Porcentajes configurables vía "
        "`KLAVE_COSTING_CONFIG_PATH`."
    )
