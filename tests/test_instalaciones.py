"""La biblioteca de instalaciones: propone, no aplica, y no propone lo que ya
está asignado ni lo que no es de su disciplina."""

from klave_engine.costing.catalog import build_default_catalog
from klave_engine.costing.instalaciones import (
    CODIGOS,
    CODIGOS_CON_REGLA,
    conceptos_de_instalaciones,
    sugerir_mapeos,
)
from klave_engine.costing.models import CostingAssumptions


def _inventario(*sheets: dict) -> dict:
    return {"unit": "m", "sheets": list(sheets)}


def _hoja(discipline: str, *, runs=(), blocks=(), label="hoja.dwg") -> dict:
    return {
        "sheet": label, "label": label, "discipline": discipline,
        "runs": list(runs), "blocks": list(blocks), "tags": [], "areas": [],
    }


def _run(layer: str, metros: float) -> dict:
    return {"layer": layer, "length_m": metros, "segments": 10, "by_view": {}}


def _block(name: str, count: int, layer: str = "X") -> dict:
    return {"block_name": name, "layer": layer, "count": count, "by_view": {}}


def test_una_capa_sanitaria_se_propone_con_sus_metros():
    inv = _inventario(_hoja("sanitaria", runs=[_run("00-SANITARIA", 128.27)]))
    sugerencias = sugerir_mapeos(inv)
    assert len(sugerencias) == 1
    s = sugerencias[0]
    assert s.kind == "layer" and s.patron == "00-SANITARIA"
    assert s.concepto == "SAN-002" and s.unidad == "M"
    assert s.cantidad == 128.27
    assert "albañal" in s.razon
    assert s.hojas == ["hoja.dwg"]


def test_la_disciplina_evita_confundir_el_fondo_arquitectonico():
    """En la hoja de aire acondicionado conviven el ducto y los muros del
    dibujo de fondo. Sin el filtro habría que adivinar."""
    inv = _inventario(
        _hoja(
            "aire",
            runs=[
                _run("AireDucto", 52.22),
                _run("MUROS2", 151.06),
                _run("PLAFONES", 92.4),
                _run("COLUMNA", 119.05),
            ],
        )
    )
    propuestos = {s.patron for s in sugerir_mapeos(inv)}
    assert propuestos == {"AireDucto"}


def test_una_capa_sanitaria_en_una_hoja_electrica_no_se_propone():
    inv = _inventario(_hoja("electrica", runs=[_run("00-SANITARIA", 100.0)]))
    assert sugerir_mapeos(inv) == []


def test_lo_ya_asignado_no_se_vuelve_a_proponer():
    """La asignación del taller manda sobre la biblioteca, siempre."""
    inv = _inventario(_hoja("gas", runs=[_run("GAS", 44.01)]))
    assert len(sugerir_mapeos(inv)) == 1
    existentes = [{"kind": "layer", "pattern": "GAS", "concept_code": "GAS-001"}]
    assert sugerir_mapeos(inv, existentes) == []


def test_un_concepto_que_el_taller_borro_no_se_propone():
    inv = _inventario(_hoja("gas", runs=[_run("GAS", 44.01)]))
    assert sugerir_mapeos(inv, [], codigos_catalogo={"HID-001"}) == []


def test_el_mismo_nombre_en_dos_hojas_es_un_solo_mapeo():
    """Así lo guarda la tabla de asignaciones, así hay que proponerlo."""
    inv = _inventario(
        _hoja("sanitaria", runs=[_run("00-SANITARIA", 60.0)], label="a.dwg"),
        _hoja("sanitaria", runs=[_run("00-SANITARIA", 40.0)], label="b.dwg"),
    )
    sugerencias = sugerir_mapeos(inv)
    assert len(sugerencias) == 1
    assert sugerencias[0].cantidad == 100.0
    assert sugerencias[0].hojas == ["a.dwg", "b.dwg"]


def test_los_bloques_se_cuentan_en_piezas_o_salidas():
    inv = _inventario(_hoja("sanitaria", blocks=[_block("DESCSAN1", 16)]))
    s = sugerir_mapeos(inv)[0]
    assert s.kind == "block" and s.concepto == "SAN-001"
    assert s.unidad == "SAL" and s.cantidad == 16.0


def test_retorno_a_secas_no_alcanza_para_proponer_agua_caliente():
    """«SEB - Retorno Filtrado» es el retorno de la filtración de una alberca,
    no el de agua caliente. Un patrón demasiado ancho convierte una
    convención de dibujo en dinero equivocado."""
    inv = _inventario(
        _hoja(
            "hidraulica",
            runs=[_run("SEB - Retorno Filtrado", 3.57), _run("P-04IH-RPIP", 39.95)],
        )
    )
    propuestos = {s.patron for s in sugerir_mapeos(inv)}
    assert propuestos == {"P-04IH-RPIP"}


def test_lo_mas_grande_va_primero():
    inv = _inventario(
        _hoja("sanitaria", runs=[_run("00-SANITARIA", 20.0), _run("00_I PLUVIAL", 180.0)])
    )
    assert [s.patron for s in sugerir_mapeos(inv)] == ["00_I PLUVIAL", "00-SANITARIA"]


def test_una_capa_sin_metros_no_produce_propuesta():
    inv = _inventario(_hoja("gas", runs=[_run("GAS", 0.0)]))
    assert sugerir_mapeos(inv) == []


def test_sin_levantamiento_no_hay_nada_que_proponer():
    assert sugerir_mapeos(None) == []
    assert sugerir_mapeos({}) == []


def test_los_conceptos_entran_al_catalogo_sin_matriz():
    """El plano sostiene la cantidad; el precio no lo sostiene nadie todavía,
    y por eso ningún concepto de instalaciones trae matriz."""
    conceptos = conceptos_de_instalaciones()
    assert {c.code for c in conceptos} == set(CODIGOS)
    assert all(
        any("Adopta un P.U." in a for a in c.assumptions) for c in conceptos
    )


def test_los_que_el_motor_sabe_leer_traen_regla_y_los_demas_no():
    """Un concepto con regla se cuantifica solo del plano; uno sin regla espera
    una asignación del levantamiento. La diferencia se dice en la línea."""
    por_codigo = {c.code: c for c in conceptos_de_instalaciones()}
    assert set(CODIGOS_CON_REGLA) <= set(por_codigo)
    for code in CODIGOS_CON_REGLA:
        assert por_codigo[code].rule is not None
        assert any("leída del plano" in a for a in por_codigo[code].assumptions)
    # HID-002 (agua caliente por mueble) es decisión de proyecto, no algo que
    # se derive del mueble: se queda sin regla a propósito.
    assert "HID-002" not in CODIGOS_CON_REGLA
    assert por_codigo["HID-002"].rule is None


def test_el_catalogo_por_omision_ya_los_incluye():
    codigos = {c.code for c in build_default_catalog(CostingAssumptions())}
    assert set(CODIGOS) <= codigos


def test_ningun_concepto_de_instalaciones_llega_con_precio():
    """Un concepto sin matriz no se prices en cero: no se prices."""
    from klave_engine.costing.apu import build_all_apus

    apus = build_all_apus(build_default_catalog(CostingAssumptions()))
    assert not (set(CODIGOS) & set(apus))


def test_una_cantidad_mapeada_sin_matriz_entra_sin_precio_y_no_se_pierde():
    """Tirar la cantidad porque falta el precio borra del presupuesto algo que
    sí está en la obra. Así se pierden partidas enteras de instalaciones."""
    from klave_engine.costing.levantamiento import apply_inventory
    from klave_engine.costing.models import BillOfQuantities

    boq = BillOfQuantities(project_id="p", currency="MXN", lines=[])
    catalog = build_default_catalog(CostingAssumptions())
    inventory = {
        "unit": "m",
        "sheets": [
            {
                "sheet": "s.dxf", "label": "sanitario.dwg", "discipline": "sanitaria",
                "runs": [{"layer": "00-SANITARIA", "length_m": 128.27, "segments": 83}],
                "blocks": [], "tags": [], "areas": [],
            }
        ],
    }
    mappings = [{"kind": "layer", "pattern": "00-SANITARIA", "concept_code": "SAN-002"}]

    assert apply_inventory(boq, catalog, {}, inventory, mappings) == 1
    linea = next(x for x in boq.lines if x.concept_code == "SAN-002")
    assert linea.quantity == 128.27
    assert linea.unpriced is True and linea.amount == 0.0
    assert any("128.27 m «00-SANITARIA»" in a for a in linea.assumptions)
    assert any("entran sin costo" in w for w in boq.warnings)


def test_cada_concepto_dice_de_donde_salio_su_cantidad_en_sus_propios_terminos():
    """Un vano no sale de «las hojas de instalaciones»: sale de un símbolo de
    puerta o ventana. La evidencia tiene que decir la verdad de cada uno."""
    por_codigo = {c.code: c for c in conceptos_de_instalaciones()}
    assert "por pieza" in por_codigo["CAN-001"].assumptions[0]
    assert "cuadro de vanos" in por_codigo["CAN-001"].assumptions[0]
    assert "metros de trazo" in por_codigo["HID-003"].assumptions[0]
    assert "símbolo insertado" in por_codigo["SAN-001"].assumptions[0]
    assert "levantamiento" in por_codigo["HID-002"].assumptions[0]


def test_la_linea_carga_el_diametro_que_el_plano_declaro():
    """«Tubería de agua fría» no la cotiza nadie; «de 102 mm (4")» sí."""
    from klave_engine.costing.boq import generate_bill_of_quantities
    from klave_engine.costing.catalog import build_default_catalog
    from klave_engine.detection.results import DetectionType, make_detection
    from klave_engine.dxf.units import DrawingUnits

    def _corrida(det_id: str, metros: float, diametro: str) -> object:
        return make_detection(
            det_id, DetectionType.pipe_run, "00-SANITARIA", (0, 0, 10, 1), 0.78, [det_id],
            "layer_run", [], {
                "run_family": "sanitaria", "discipline": "sanitaria",
                "estimated_length": metros, "length_m": metros, "diametro": diametro,
            }, "s.dxf",
        )

    catalog = [c for c in build_default_catalog(CostingAssumptions()) if c.code == "SAN-002"]
    units = DrawingUnits(unit="m", source="declared", confidence=1.0)
    boq = generate_bill_of_quantities(
        "p", [_corrida("r1", 60.0, '102 mm (4")'), _corrida("r2", 40.0, '102 mm (4")')],
        units, catalog, {}, "MXN",
    )
    linea = next(x for x in boq.lines if x.concept_code == "SAN-002")
    # La especificación entra a la identidad, antes de «incluye»: pegada al
    # final caía dentro del alcance, donde no identifica nada.
    assert 'de 102 mm (4"), incluye' in linea.description
    assert not linea.description.endswith('(4")')
    assert linea.quantity == 100.0


def test_dos_diametros_en_una_linea_se_dicen_en_vez_de_fingirse_uno():
    """Cada diámetro tiene su precio: presupuestarlos juntos es esconder que
    el renglón vale dos cosas distintas."""
    from klave_engine.costing.boq import generate_bill_of_quantities
    from klave_engine.costing.catalog import build_default_catalog
    from klave_engine.detection.results import DetectionType, make_detection
    from klave_engine.dxf.units import DrawingUnits

    def _corrida(det_id: str, diametro: str) -> object:
        return make_detection(
            det_id, DetectionType.pipe_run, "00-SANITARIA", (0, 0, 10, 1), 0.78, [det_id],
            "layer_run", [], {
                "run_family": "sanitaria", "discipline": "sanitaria",
                "estimated_length": 50.0, "length_m": 50.0, "diametro": diametro,
            }, "s.dxf",
        )

    catalog = [c for c in build_default_catalog(CostingAssumptions()) if c.code == "SAN-002"]
    boq = generate_bill_of_quantities(
        "p", [_corrida("r1", '102 mm (4")'), _corrida("r2", '51 mm (2")')],
        DrawingUnits(unit="m", source="declared", confidence=1.0), catalog, {}, "MXN",
    )
    linea = next(x for x in boq.lines if x.concept_code == "SAN-002")
    assert "mm" not in linea.description  # no se elige uno de los dos
    assert any("2 diámetros distintos" in w for w in boq.warnings)


def test_la_linea_carga_el_material_junto_al_diametro():
    """«Tubería de gas» no la cotiza nadie; «de PEAD de 19 mm (3/4")» es como
    la publican los tabuladores."""
    from klave_engine.costing.boq import generate_bill_of_quantities
    from klave_engine.costing.catalog import build_default_catalog
    from klave_engine.detection.results import DetectionType, make_detection
    from klave_engine.dxf.units import DrawingUnits

    corrida = make_detection(
        "g1", DetectionType.pipe_run, "GAS", (0, 0, 10, 1), 0.78, ["g1"],
        "layer_run", [], {
            "run_family": "gas", "discipline": "gas",
            "estimated_length": 44.0, "length_m": 44.0,
            "diametro": '19 mm (3/4")', "material": "PEAD",
        }, "g.dxf",
    )
    catalog = [c for c in build_default_catalog(CostingAssumptions()) if c.code == "GAS-001"]
    boq = generate_bill_of_quantities(
        "p", [corrida], DrawingUnits(unit="m", source="declared", confidence=1.0),
        catalog, {}, "MXN",
    )
    linea = next(x for x in boq.lines if x.concept_code == "GAS-001")
    assert 'de PEAD de 19 mm (3/4"), incluye' in linea.description
