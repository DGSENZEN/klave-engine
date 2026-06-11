"""Klave Engine — Costs Engineering dashboard (entry point).

Navigation mirrors the cost engineering workflow:
plano → detecciones → presupuesto → precios unitarios → integración →
programa de obra → flujo financiero → riesgos.
"""

import streamlit as st
from views import (
    detecciones,
    finanzas,
    grafo,
    integracion,
    plano,
    precios_unitarios,
    presupuesto,
    programa,
    resumen,
    riesgos,
)

st.set_page_config(
    page_title="Klave Engine — Ingeniería de Costos",
    page_icon="🏗️",
    layout="wide",
)

navigation = st.navigation(
    {
        "Proyecto": [
            st.Page(resumen.render, title="Resumen", icon="📋", url_path="resumen",
                    default=True),
            st.Page(plano.render, title="Visor del Plano", icon="📐", url_path="plano"),
            st.Page(detecciones.render, title="Detecciones", icon="🔎",
                    url_path="detecciones"),
            st.Page(grafo.render, title="Grafo", icon="🕸️", url_path="grafo"),
            st.Page(riesgos.render, title="Riesgos", icon="⚠️", url_path="riesgos"),
        ],
        "Ingeniería de Costos": [
            st.Page(presupuesto.render, title="Presupuesto", icon="🧾",
                    url_path="presupuesto"),
            st.Page(precios_unitarios.render, title="Precios Unitarios", icon="🧮",
                    url_path="precios-unitarios"),
            st.Page(integracion.render, title="Integración de Costos", icon="💰",
                    url_path="integracion"),
        ],
        "Planeación y Finanzas": [
            st.Page(programa.render, title="Programa de Obra", icon="🗓️",
                    url_path="programa"),
            st.Page(finanzas.render, title="Flujo Financiero", icon="📈",
                    url_path="finanzas"),
        ],
    }
)
navigation.run()
