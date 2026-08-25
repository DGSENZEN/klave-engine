"""Precios para las pruebas, declarados aquí y en ningún otro lado.

El producto ya no trae precios sembrados: un precio que nadie cotizó no es un
precio, y los que traía los había escrito yo. Pero las pruebas que ejercitan
el dinero —que una cantidad por un P.U. da un importe, que un ajuste mueve el
total, que la explosión suma lo que las matrices consumen— necesitan alguno.

Que vivan aquí es la diferencia entre un supuesto a la vista y uno escondido
en la semilla del producto. Estos números no son de campo, no salen de
ninguna publicación y no deben usarse para presupuestar nada: son la escala
mínima para que las cuentas se puedan verificar.
"""

from klave_engine.costing.insumos import RESOURCES
from klave_engine.costing.models import Resource, ResourceType

# Insumo → costo unitario de prueba. Valores redondos a propósito: si una
# prueba falla, el número dice de dónde salió.
PRECIOS: dict[str, float] = {
    "MAT-ACERO": 26_500.0, "MAT-ADHESIVO": 9.5, "MAT-AGUA": 35.0, "MAT-ALAMBRE": 38.0,
    "MAT-ARENA": 420.0, "MAT-BLOCK": 185.0, "MAT-BOVEDILLA": 24.0, "MAT-CEM": 3_350.0,
    "MAT-CIMBRA": 210.0, "MAT-CLAVO": 42.0, "MAT-CONC150": 2_100.0, "MAT-CONC250": 2_650.0,
    "MAT-GRAVA": 460.0, "MAT-MADERA": 28.0, "MAT-MALLA": 85.0, "MAT-MALLA66": 62.0,
    "MAT-MORTERO": 1_850.0, "MAT-PINTURA": 78.0, "MAT-PISO-CER": 185.0,
    "MAT-PLANTILLA": 1_450.0, "MAT-SELLADOR": 32.0, "MAT-TEPETATE": 260.0,
    "MAT-VIGUETA": 98.0, "MAT-YESO": 4.2,
    "MO-AYUD": 700.0, "MO-CUAD-ALB": 1_750.0, "MO-CUAD-CARP": 1_780.0,
    "MO-CUAD-FIE": 1_820.0, "MO-FIERRERO": 830.0, "MO-OF-ALB": 1_050.0,
    "MO-PEON": 620.0, "MO-PINTOR": 1_180.0, "MO-YESERO": 1_260.0,
    "EQ-BAILARINA": 650.0, "EQ-CAMION": 780.0, "EQ-MOTOCONFORMADORA": 1_650.0,
    "EQ-PERFORADORA": 2_850.0, "EQ-PIPA": 650.0, "EQ-RETRO": 720.0,
    "EQ-REVOLVEDORA": 380.0, "EQ-TOPOGRAFIA": 850.0, "EQ-VIBRADOR": 290.0,
    "EQ-VIBROCOMPACTADOR": 1_100.0,
}


def libro() -> dict[str, Resource]:
    """El catálogo de insumos del producto, con los precios de prueba puestos.

    Los insumos que el producto define sin precio —que ahora son todos salvo
    la herramienta menor, que es un porcentaje— toman el suyo de la tabla de
    arriba; el que no esté en ella se queda sin precio, y el concepto que lo
    use se queda sin matriz, que es justo lo que hay que poder probar."""
    salida: dict[str, Resource] = {}
    for code, recurso in RESOURCES.items():
        precio = PRECIOS.get(code)
        salida[code] = (
            recurso if precio is None else recurso.model_copy(update={"unit_cost": precio})
        )
    # Insumos que sólo existen en el catálogo del taller (sembrados por
    # migración) y que algunas pruebas usan sin pasar por el store.
    for code, precio in PRECIOS.items():
        if code in salida:
            continue
        salida[code] = Resource(
            code=code, description=f"Insumo de prueba {code}", unit="JOR",
            unit_cost=precio,
            resource_type=(
                ResourceType.labor if code.startswith("MO-")
                else ResourceType.equipment if code.startswith("EQ-")
                else ResourceType.material
            ),
        )
    return salida


LIBRO: dict[str, Resource] = libro()


def sembrar(store: object) -> int:
    """Carga los precios de prueba en el catálogo de un taller.

    Es el camino real: el producto sabe qué insumos existen y el taller pone
    lo que le cuestan. Las pruebas que van por el store —matrices, alias,
    acero— tienen que pasar por aquí en vez de esperar precios sembrados,
    porque esperar precios sembrados era el problema."""
    puestos = 0
    for code, precio in PRECIOS.items():
        store.upsert_insumo(  # type: ignore[attr-defined]
            code, unit_cost=precio, source="Precios de prueba",
            source_type="cotizacion", vigencia="2026-08",
        )
        puestos += 1
    return puestos
