import streamlit as st
from common import load_artifact, money, select_project_root


def render() -> None:
    st.title("Resumen del Proyecto")
    root = select_project_root()
    if root is None:
        return

    manifest = load_artifact(root, "project_manifest.json")
    units = load_artifact(root, "drawing_units.json")
    detections = load_artifact(root, "detections.json")
    costs = load_artifact(root, "cost_report.json")
    entities_summary = load_artifact(root, "spatial_index_summary.json")

    if manifest:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Planos fuente", len(manifest["source_files"]))
        col2.metric("Estado", manifest["processing_status"])
        col3.metric(
            "Entidades",
            f"{entities_summary['entity_count']:,}" if entities_summary else "—",
        )
        col4.metric("Detecciones", f"{len(detections):,}" if detections else "—")

    if units:
        confidence = f"{units['confidence']:.0%}"
        st.info(
            f"**Unidades del plano:** {units['unit']} — fuente: {units['source']} "
            f"(confianza {confidence})"
        )

    if costs:
        st.subheader("Indicadores de costo")
        integration = costs["integration"]
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Costo directo", money(integration["direct_cost"]))
        col2.metric("Precio de venta", money(integration["sale_price"]))
        col3.metric("Total c/ contingencia", money(integration["grand_total"]))
        months = len(costs["financial"]["periods"])
        col4.metric(
            "Duración estimada",
            f"{costs['schedule']['total_duration_days']} días (~{months} meses)",
        )
        if costs["boq"]["totals_by_phase"]:
            st.subheader("Costo directo por fase")
            st.bar_chart(costs["boq"]["totals_by_phase"], horizontal=True)

    if manifest and manifest.get("errors"):
        st.subheader("Errores registrados")
        for error in manifest["errors"]:
            st.error(error)

    layers = load_artifact(root, "layer_summary.json")
    if layers:
        with st.expander(f"Resumen de capas ({len(layers)})"):
            st.dataframe(layers, use_container_width=True)
