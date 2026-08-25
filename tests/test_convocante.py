"""El catálogo de la convocante manda sobre qué se cotiza; el plano dice si
sus cantidades se sostienen."""

from klave_engine.costing.convocante import atar_catalogo, avisos_de_cantidad
from klave_engine.costing.models import (
    BillOfQuantities,
    BoqLine,
    Concept,
    QuantityKind,
    QuantityRule,
)
from klave_engine.costing.sources.presupuesto import PresupuestoRow


def _fila(clave: str, desc: str, unidad: str, cantidad: float, grupo: str = "") -> PresupuestoRow:
    return PresupuestoRow(clave=clave, description=desc, unit=unidad,
                          quantity=cantidad, price=None, group=grupo)


def _concepto(code: str, desc: str, unidad: str, fase: str = "Estructura") -> Concept:
    """Un concepto del motor: lleva regla, que es lo que lo hace medible."""
    from klave_engine.detection.results import DetectionType

    return Concept(
        code=code, description=desc, unit=unidad, phase=fase,
        production_rate_per_day=20.0,
        rule=QuantityRule(
            detection_type=DetectionType.wall, kind=QuantityKind.AREA,
            source_property="estimated_area",
        ),
    )


def _boq(**cantidades: float) -> BillOfQuantities:
    return BillOfQuantities(
        project_id="p", currency="MXN",
        lines=[
            BoqLine(concept_code=code, description=code, unit="M2", quantity=q,
                    unit_price=0.0, amount=0.0, phase="Estructura", raw_quantity=q,
                    raw_kind=QuantityKind.AREA, source_detection_count=1, confidence=0.9)
            for code, q in cantidades.items()
        ],
    )


_CATALOGO = [_concepto("EST-004", "Muros de block/concreto, incluye refuerzo y mortero", "M2")]


def test_el_orden_y_las_claves_de_la_convocante_se_respetan():
    """La propuesta se devuelve en su documento: ni una clave más, ni una
    menos, ni en otro orden."""
    filas = [
        _fila("OP-03", "Muros de block de concreto", "M2", 420.0),
        _fila("OP-01", "Trazo y nivelación", "M2", 300.0),
        _fila("OP-02", "Excavación a mano", "M3", 45.0),
    ]
    cat = atar_catalogo(filas, _CATALOGO, nombre="Licitación 2026-01")
    assert [r.clave for r in cat.renglones] == ["OP-03", "OP-01", "OP-02"]
    assert [r.orden for r in cat.renglones] == [0, 1, 2]
    assert [r.quantity for r in cat.renglones] == [420.0, 300.0, 45.0]


def test_cada_renglon_se_ata_al_concepto_que_el_motor_sabe_medir():
    filas = [_fila("OP-03", "Muro de block de concreto con refuerzo", "M2", 420.0)]
    cat = atar_catalogo(filas, _CATALOGO, _boq(**{"EST-004": 507.0}))
    renglon = cat.renglones[0]
    assert renglon.concept_code == "EST-004"
    assert renglon.match_score >= 0.55
    assert renglon.quantity_engine == 507.0


def test_lo_que_no_se_ata_con_confianza_se_deja_para_que_alguien_lo_ate():
    """Atarlo mal es más caro que no atarlo."""
    filas = [_fila("OP-99", "Suministro de mobiliario de oficina", "PZA", 12.0)]
    cat = atar_catalogo(filas, _CATALOGO)
    assert cat.renglones[0].concept_code == ""
    assert cat.sin_atar == cat.renglones
    assert any("atados" in n for n in cat.notas)


def test_el_catalogo_con_menos_cantidad_que_el_plano_avisa_de_obra_no_pagada():
    """Se ejecuta y no se cataloga: la paga el licitante con sus indirectos."""
    filas = [_fila("OP-03", "Muro de block de concreto con refuerzo", "M2", 420.0)]
    cat = atar_catalogo(filas, _CATALOGO, _boq(**{"EST-004": 507.0}))
    aviso = " ".join(avisos_de_cantidad(cat))
    assert "menos cantidad que el plano" in aviso
    assert "420.00" in aviso and "507.00" in aviso
    assert "indirectos" in aviso


def test_el_catalogo_con_mas_cantidad_que_el_plano_avisa_de_monto_sin_obra():
    """Es monto de propuesta sin obra detrás, y eso se cae en la evaluación."""
    filas = [_fila("OP-03", "Muro de block de concreto con refuerzo", "M2", 600.0)]
    cat = atar_catalogo(filas, _CATALOGO, _boq(**{"EST-004": 420.0}))
    aviso = " ".join(avisos_de_cantidad(cat))
    assert "más cantidad que el plano" in aviso
    assert "junta" in aviso


def test_una_diferencia_de_redondeo_no_es_un_aviso():
    """Una alarma por 2 % gasta la atención que hace falta para la de 20 %."""
    filas = [_fila("OP-03", "Muro de block de concreto con refuerzo", "M2", 500.0)]
    cat = atar_catalogo(filas, _CATALOGO, _boq(**{"EST-004": 510.0}))
    assert avisos_de_cantidad(cat) == []


def test_el_motor_no_corrige_las_cantidades_de_la_convocante():
    """Son el contrato: cambiarlas por las del plano sería presentar otra
    propuesta."""
    filas = [_fila("OP-03", "Muro de block de concreto con refuerzo", "M2", 420.0)]
    cat = atar_catalogo(filas, _CATALOGO, _boq(**{"EST-004": 507.0}))
    assert cat.renglones[0].quantity == 420.0
    assert cat.renglones[0].quantity_engine == 507.0


def test_el_importe_sale_de_la_cantidad_catalogada_y_del_precio_del_licitante():
    filas = [_fila("OP-03", "Muro de block de concreto con refuerzo", "M2", 420.0)]
    cat = atar_catalogo(filas, _CATALOGO, _boq(**{"EST-004": 507.0}),
                        precios={"EST-004": 585.13})
    assert cat.renglones[0].amount == round(420.0 * 585.13, 2)
    assert cat.total == round(420.0 * 585.13, 2)
    assert cat.sin_precio == []


def test_un_renglon_sin_precio_se_ve_y_no_vale_cero():
    filas = [
        _fila("OP-03", "Muro de block de concreto con refuerzo", "M2", 420.0),
        _fila("OP-99", "Suministro de mobiliario", "PZA", 12.0),
    ]
    cat = atar_catalogo(filas, _CATALOGO, precios={"EST-004": 585.13})
    sin = cat.sin_precio
    assert [r.clave for r in sin] == ["OP-99"]
    assert sin[0].amount is None


def test_se_prefiere_el_concepto_que_el_motor_mide():
    """Un concepto importado de un catálogo de destajos puede parecerse más en
    palabras y no tiene cantidad leída del plano: atar ahí pierde la
    comparación, que es lo único que el motor aporta sobre el catálogo."""
    catalogo = [
        _concepto("SAN-002", "Tubería sanitaria de albañal", "M", "Instalación sanitaria"),
        # Importado de un destajo: se llama casi igual y no mide nada.
        Concept(code="N1-SAN-SN-01", description="Línea sanitaria tubo PVC 100 mm",
                unit="M", phase="Destajos", rule=None, production_rate_per_day=20.0),
    ]
    filas = [_fila("OP-001", "Línea sanitaria con tubo de PVC de 100 mm", "M", 150.0)]
    cat = atar_catalogo(filas, catalogo, _boq(**{"SAN-002": 167.75}))
    assert cat.renglones[0].concept_code == "SAN-002"
    assert cat.renglones[0].quantity_engine == 167.75


def test_si_ninguno_del_motor_alcanza_se_mira_el_resto():
    """El taller también cotiza cosas que el motor no sabe leer del plano."""
    catalogo = [
        _concepto("EST-004", "Muros de block/concreto", "M2"),
        Concept(code="MOB-01", description="Suministro y colocación de mobiliario de oficina",
                unit="PZA", phase="Mobiliario", rule=None, production_rate_per_day=8.0),
    ]
    filas = [_fila("OP-007", "Suministro y colocación de mobiliario de oficina", "PZA", 24.0)]
    cat = atar_catalogo(filas, catalogo)
    assert cat.renglones[0].concept_code == "MOB-01"
    assert cat.renglones[0].quantity_engine is None
