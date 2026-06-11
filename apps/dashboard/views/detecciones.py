import streamlit as st
from common import DETECTION_LABELS_ES, load_artifact, select_project_root


def render() -> None:
    st.title("Detecciones")
    root = select_project_root()
    if root is None:
        return
    detections = load_artifact(root, "detections.json")
    if not detections:
        return

    counts: dict[str, int] = {}
    for detection in detections:
        label = DETECTION_LABELS_ES.get(
            detection["detection_type"], detection["detection_type"]
        )
        counts[label] = counts.get(label, 0) + 1
    st.bar_chart(counts, horizontal=True)

    types = sorted({d["detection_type"] for d in detections})
    col1, col2 = st.columns(2)
    selected = col1.selectbox(
        "Tipo", ["(todos)"] + types,
        format_func=lambda t: DETECTION_LABELS_ES.get(t, t),
    )
    min_confidence = col2.slider("Confianza mínima", 0.0, 1.0, 0.0, 0.05)
    filtered = [
        d
        for d in detections
        if (selected == "(todos)" or d["detection_type"] == selected)
        and d["confidence"] >= min_confidence
    ]
    st.caption(f"{len(filtered):,} de {len(detections):,} detecciones")
    st.dataframe(
        [
            {
                "id": d["detection_id"],
                "tipo": DETECTION_LABELS_ES.get(d["detection_type"], d["detection_type"]),
                "etiqueta": d["label"],
                "confianza": d["confidence"],
                "evidencia": "; ".join(d["evidence"]["notes"][:2]),
            }
            for d in filtered
        ],
        use_container_width=True,
        height=420,
    )

    with st.expander("Inspeccionar una detección"):
        detection_id = st.text_input("ID de la detección (p.ej. det_000001)")
        if detection_id:
            match = next(
                (d for d in detections if d["detection_id"] == detection_id), None
            )
            st.json(match) if match else st.warning("No se encontró ese ID")
