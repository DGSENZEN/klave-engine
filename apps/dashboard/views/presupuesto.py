import streamlit as st
from common import load_artifact, money, select_project_root


def render() -> None:
    st.title("Catálogo de Conceptos y Presupuesto")
    root = select_project_root()
    if root is None:
        return
    costs = load_artifact(root, "cost_report.json")
    if not costs:
        return
    boq = costs["boq"]

    col1, col2, col3 = st.columns(3)
    col1.metric("Costo directo", money(boq["direct_cost_total"]))
    col2.metric("Conceptos con cantidades", len(boq["lines"]))
    confidence = (
        sum(line["confidence"] for line in boq["lines"]) / len(boq["lines"])
        if boq["lines"]
        else 0
    )
    col3.metric("Confianza promedio", f"{confidence:.0%}")

    st.dataframe(
        [
            {
                "Clave": line["concept_code"],
                "Concepto": line["description"],
                "Unidad": line["unit"],
                "Cantidad": round(line["quantity"], 2),
                "P.U. (CD)": line["unit_price"],
                "Importe": line["amount"],
                "Fase": line["phase"],
                "Confianza": line["confidence"],
                "Detecciones": line["source_detection_count"],
            }
            for line in boq["lines"]
        ],
        use_container_width=True,
    )

    csv_path = root / "reports" / "presupuesto.csv"
    if csv_path.exists():
        st.download_button(
            "Descargar presupuesto (CSV)",
            csv_path.read_text(encoding="utf-8"),
            file_name="presupuesto.csv",
            mime="text/csv",
        )

    if boq["totals_by_phase"]:
        st.subheader("Importe por fase")
        st.bar_chart(boq["totals_by_phase"], horizontal=True)

    with st.expander("Supuestos del presupuesto"):
        for assumption in boq["assumptions"]:
            st.write(f"- {assumption}")
        for line in boq["lines"]:
            for assumption in line["assumptions"]:
                st.write(f"- **[{line['concept_code']}]** {assumption}")
    if boq["warnings"]:
        with st.expander(f"Advertencias ({len(boq['warnings'])})"):
            for warning in boq["warnings"]:
                st.warning(warning)
