"""El catálogo de la obra de ejemplo: el catálogo base de Klave con precios
didácticos, para que el recorrido muestre un presupuesto con precio sin tocar
el catálogo del taller. Cada precio dice que es de la obra de ejemplo."""

from __future__ import annotations

import json
from pathlib import Path

from klave_engine.costing.catalog_store import CatalogStore

PRECIOS = Path(__file__).with_name("precios_didacticos.json")
FUENTE = "Obra de ejemplo — precios didácticos"
VIGENCIA = "2026-10"


def sembrar_catalogo_didactico(store: CatalogStore) -> int:
    """Pone precio a los insumos de la obra didáctica y agrega las claves del
    taller ficticio a las que el recorrido enseña a mapear; devuelve cuántos
    insumos tienen precio. Sembrar dos veces no duplica nada."""
    datos = json.loads(PRECIOS.read_text(encoding="utf-8"))
    precios: dict[str, float] = datos["insumos"]
    existentes = {row["code"] for row in store.list_insumos()}
    sembrados = 0
    for code, costo in precios.items():
        if code not in existentes:
            continue
        store.upsert_insumo(
            code, unit_cost=costo, source=FUENTE, source_type="referencia", vigencia=VIGENCIA
        )
        sembrados += 1
    existentes_conceptos = {row["code"] for row in store.load_concepts()}
    for concepto in datos.get("conceptos_del_taller", []):
        if concepto["code"] in existentes_conceptos:
            continue
        store.create_concept(
            code=concepto["code"],
            description=concepto["description"],
            unit=concepto["unit"],
            phase=concepto["phase"],
            production_rate_per_day=concepto["production_rate_per_day"],
            components=[(codigo, cantidad) for codigo, cantidad in concepto["components"]],
            import_source=FUENTE,
        )
    return sembrados
