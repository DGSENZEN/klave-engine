"""Lo que el copiloto puede hacer: derivado del diagnóstico, con la fuente a
la vista, y nada aplicado sin que alguien lo acepte."""

from klave_engine.copilot.acciones import _misma_unidad, proponer
from klave_engine.costing.hallazgos import diagnose

from tests.test_hallazgos import _line, _report


class _Catalogo:
    """Un catálogo de referencia con lo justo para la prueba."""

    def __init__(self, filas):
        self._filas = filas

    def list_reference_rows(self):
        return self._filas


def _referencia(ref_id, fc, unidad="M3", precio=4493.63, fuente="Tabulador CDMX"):
    return {
        "ref_id": ref_id,
        "clave": f"FE{ref_id}",
        "description": f"Suministro y colocación de concreto hidráulico f'c= {fc} kg/cm2",
        "unit": unidad,
        "price": precio,
        "source_name": fuente,
        "source_key": "cdmx-tabulador-2026-06",
    }


_CONFLICTO = (
    "CIM-002: El plano declara f'c=300 para cimentacion; el concepto costea f'c=250."
)


def test_propone_adoptar_el_precio_publicado_del_fc_correcto():
    report = _report([_line("CIM-002", quantity=10.0, amount=36322.7)], warnings=[_CONFLICTO])
    catalogo = _Catalogo([_referencia(11, 300)])
    acciones = proponer(report, diagnose(report), catalogo, "p")

    accion = next(a for a in acciones if a.tipo == "adoptar_precio_publicado")
    assert accion.peticiones[0]["concepto"] == "CIM-002"
    assert accion.peticiones[0]["body"]["ref_id"] == 11
    cambio = accion.vista_previa[0]
    assert "f'c=250" in cambio.de and "f'c=300" in cambio.a
    assert "Tabulador CDMX" in cambio.a  # la procedencia viaja en la propuesta
    assert accion.reversible  # cómo deshacerlo se dice antes de hacerlo


def test_la_descripcion_se_corrige_al_fc_que_se_va_a_cobrar():
    """La descripción es lo que firma el cliente: cobrar f'c=300 y seguir
    diciendo 250 sería el mismo desacuerdo con el plano, al revés."""
    report = _report([_line("CIM-002", quantity=10.0, amount=36322.7)], warnings=[_CONFLICTO])
    report.boq.lines[0].description = "Concreto f'c=250 kg/cm² en zapatas y dados"
    acciones = proponer(report, diagnose(report), _Catalogo([_referencia(11, 300)]), "p")
    peticion = acciones[0].peticiones[0]
    assert peticion["descripcion"] == "Concreto f'c=300 kg/cm² en zapatas y dados"


def test_una_referencia_en_otra_unidad_no_se_propone():
    """Un precio por m³ sobre un concepto que se mide en m² multiplica mal por
    un factor que nadie nota hasta la obra."""
    report = _report([_line("EST-012", quantity=100.0, amount=50000.0, unit="M2")],
                     warnings=["EST-012: El plano declara f'c=350 para losa; "
                               "el concepto costea f'c=250."])
    catalogo = _Catalogo([_referencia(12, 350, unidad="M3")])
    acciones = proponer(report, diagnose(report), catalogo, "p")
    assert not [a for a in acciones if a.tipo == "adoptar_precio_publicado"]

    # Con la referencia en la unidad correcta, sí se propone.
    ok = proponer(report, diagnose(report), _Catalogo([_referencia(13, 350, unidad="M2")]), "p")
    assert [a for a in ok if a.tipo == "adoptar_precio_publicado"]


def test_lo_que_no_tiene_fuente_se_dice_en_vez_de_inventarse():
    report = _report(
        [
            _line("CIM-002", quantity=10.0, amount=36322.7),
            _line("EST-012", quantity=100.0, amount=50000.0, unit="M2"),
        ],
        warnings=[
            _CONFLICTO,
            "EST-012: El plano declara f'c=350 para losa; el concepto costea f'c=250.",
        ],
    )
    acciones = proponer(report, diagnose(report), _Catalogo([_referencia(11, 300)]), "p")
    accion = next(a for a in acciones if a.tipo == "adoptar_precio_publicado")
    assert len(accion.peticiones) == 1  # solo el que sí tiene referencia
    assert "EST-012" in accion.descripcion  # y se nombra el que no


def test_un_concepto_sin_precio_pide_el_dato_y_no_ofrece_boton():
    """El motor no sabe cuánto cuesta: la respuesta honesta es pedirlo."""
    report = _report([_line("CIM-010", quantity=23.0, unpriced=True, unit="PZA")])
    acciones = proponer(report, diagnose(report), _Catalogo([]), "p")
    accion = next(a for a in acciones if a.tipo == "dar_precio")
    assert accion.requiere  # sin esto la interfaz no dibuja el botón
    assert accion.peticiones == []


def test_sin_hallazgos_no_hay_acciones_que_proponer():
    report = _report([_line("EST-002")])
    assert proponer(report, diagnose(report), _Catalogo([]), "p") == []


def test_las_unidades_se_comparan_con_criterio():
    assert _misma_unidad("M3", "m³")
    assert _misma_unidad("M2", "m2")
    assert not _misma_unidad("M2", "M3")
    assert not _misma_unidad("M", "M3")
