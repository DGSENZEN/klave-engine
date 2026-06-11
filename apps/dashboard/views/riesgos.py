import streamlit as st
from common import load_artifact, select_project_root

SEVERITY_ICONS = {"high": "🟥 Alta", "medium": "🟧 Media", "low": "🟨 Baja"}


def render() -> None:
    st.title("Riesgos")
    root = select_project_root()
    if root is None:
        return
    report = load_artifact(root, "risk_report.json")
    if not report:
        return

    counts = report["counts_by_severity"]
    col1, col2, col3 = st.columns(3)
    col1.metric("Alta", counts.get("high", 0))
    col2.metric("Media", counts.get("medium", 0))
    col3.metric("Baja", counts.get("low", 0))

    severity = st.selectbox("Severidad", ["(todas)", "high", "medium", "low"],
                            format_func=lambda s: SEVERITY_ICONS.get(s, "(todas)"))
    risk_types = sorted({f["risk_type"] for f in report["findings"]})
    risk_type = st.selectbox("Tipo de riesgo", ["(todos)"] + risk_types)
    filtered = [
        f
        for f in report["findings"]
        if (severity == "(todas)" or f["severity"] == severity)
        and (risk_type == "(todos)" or f["risk_type"] == risk_type)
    ]
    max_detail = 200
    st.caption(
        f"{len(filtered):,} de {len(report['findings']):,} hallazgos"
        + (f" (mostrando los primeros {max_detail})" if len(filtered) > max_detail else "")
    )
    for finding in filtered[:max_detail]:
        icon = SEVERITY_ICONS.get(finding["severity"], "")
        with st.expander(f"{icon} — {finding['risk_type']}"):
            st.write(finding["message"])
            st.write(f"**Acción recomendada:** {finding['recommended_human_action']}")
            st.json(
                {
                    "entidades": finding["source_entities"],
                    "detecciones": finding["related_detections"],
                    "evidencia": finding["evidence"],
                }
            )
