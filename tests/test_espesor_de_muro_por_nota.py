"""Tarea 15f (R275): el espesor de los muros de block que dicen las notas del plano.

Cuando las notas numeradas dicen un solo espesor de muro de block («MURO DE BLOQUE DE CONCRETO
DE 15 x 20 x 40 CM EN 15 CM. DE ESPESOR», PRUEBA-1), es una regla del proyecto (fuente ``nota``)
y cada muro de block la toma en el presupuesto: la nota manda sobre lo medido. Donde el núcleo
dibujado coincide no se dice nada más; donde sólo está el contorno y mide más (18 cm), el aviso
dice las dos cosas: el contorno incluye el aplanado. Sin esa nota, lo medido.
"""

import pytest
from klave_engine.costing.sintesis import firma, slug
from klave_engine.detection.results import Detection, DetectionType, make_detection
from klave_engine.detection.views import SheetSegmentation, ViewKind, ViewRegion
from klave_engine.estructura.dato import Dato
from klave_engine.estructura.modelo import escribir_espesor_de_muros
from klave_engine.estructura.reglas import leer_reglas, reglas_estandar

from tests.test_estructura_reglas import _dibujo

PRUEBA_1 = [
    "1.- TODOS LOS MUROS INDICADOS EN PLANTA ( ) SERAN DE CARGA Y DEBERAN",
    "LEVANTARSE ANTES DEL COLADO DE LA LOSA DEL NIVEL SUPERIOR.",
    "2.- ESPECIFICACION DE MATERIALES:",
    ("a).- MURO DE BLOQUE DE CONCRETO DE 15 x 20 x 40 CM", 0.2),
    "EN 15 CM. DE ESPESOR, TIPO INTERMEDIO, DE RESISTENCIA MINIMA",
    "A LA COMPRESION ft= 50 KG/CM2.",
]


def _reglas(tmp_path, renglones, titulo="NOTAS DE MUROS DE CARGA"):
    return leer_reglas(_dibujo(tmp_path, tabla=False, bloques=[([(titulo, renglones)], 1)]), [])


def test_la_nota_dice_el_espesor_de_los_muros_de_block(tmp_path):
    r = _reglas(tmp_path, PRUEBA_1)
    dato = r.muro_block_espesor_m
    assert dato is not None
    assert dato.valor == pytest.approx(0.15)
    assert dato.fuente == "nota"
    assert "15 CM. DE ESPESOR" in dato.texto
    # Cada hoja la resuelve igual (``Reglas.para``).
    assert r.para("x").muro_block_espesor_m.valor == pytest.approx(0.15)


def test_sin_espesor_escrito_no_hay_regla(tmp_path):
    # Marina: «MURO DE BLOQUE DE CONCRETO DE 15x20x40 CM y 20x20x40 CM» no dice un espesor.
    renglones = [
        "1.- ESPECIFICACION DE MATERIALES:",
        "a).- MURO DE BLOQUE DE CONCRETO DE 15x20x40 CM y 20x20x40 CM, TIPO INTERMEDIO.",
    ]
    assert _reglas(tmp_path, renglones).muro_block_espesor_m is None
    assert reglas_estandar().muro_block_espesor_m is None


def test_dos_espesores_distintos_no_son_una_regla_y_se_avisa(tmp_path):
    renglones = [
        "1.- MUROS DE BLOCK EN 15 CM DE ESPESOR EN PLANTA BAJA.",
        "2.- MUROS DE BLOCK EN 20 CM DE ESPESOR EN PLANTA ALTA.",
    ]
    r = _reglas(tmp_path, renglones)
    assert r.muro_block_espesor_m is None
    assert any("espesores de muro de block distintos" in a for a in r.avisos)


# --- el presupuesto: cada muro de block toma el espesor de la nota ------------------------------


def _muro(det_id: str, espesor: float, de: str | None, largo: float = 5.0, **extra) -> Detection:
    props = {"estimated_length": largo, "estimated_thickness": espesor, "wall_kind": "block",
             "layer": "A-WALL", **extra}
    if de is not None:
        props["thickness_from"] = de
    return make_detection(det_id, DetectionType.wall, det_id, (0, 0, 1, 1), 0.9, [], "m", [],
                          props)


NOTA = Dato(valor=0.15, fuente="nota", texto="La nota 2 de NOTAS DE MUROS DE CARGA")


def _con_nota(dato=NOTA):
    reglas = reglas_estandar()
    reglas.muro_block_espesor_m = dato
    return reglas


def test_el_nucleo_que_coincide_toma_la_nota_sin_aviso():
    muro = _muro("w1", 0.15, "core")
    (escrito,), avisos = escribir_espesor_de_muros([muro], _con_nota(), 1.0)
    assert escrito.properties["estimated_thickness"] == pytest.approx(0.15)
    assert escrito.properties["espesor_fuente"] == "nota"
    assert avisos == []


def test_el_contorno_de_18_toma_los_15_de_la_nota_con_su_aviso():
    muro = _muro("w2", 0.18, "outline", largo=6.6, centreline_length=6.435)
    (escrito,), avisos = escribir_espesor_de_muros([muro], _con_nota(), 1.0)
    p = escrito.properties
    assert p["estimated_thickness"] == pytest.approx(0.15)
    assert p["espesor_fuente"] == "nota"
    # El contorno incluye el aplanado: el eje del block es el del contorno.
    assert p["estimated_length"] == pytest.approx(6.435)
    (aviso,) = avisos
    dicho = "el contorno dibujado mide 18 cm; la nota dice 15: el contorno incluye el aplanado"
    assert dicho in aviso
    assert "w2" in aviso
    # La detección del detector no se toca (R235): el escrito es una copia.
    assert muro.properties["estimated_thickness"] == 0.18


def test_lo_escrito_se_deshace_al_volver_a_escribir():
    muro = _muro("w2", 0.18, "outline", largo=6.6, centreline_length=6.435)
    (escrito,), _ = escribir_espesor_de_muros([muro], _con_nota(), 1.0)
    (sin_nota,), avisos = escribir_espesor_de_muros([escrito], reglas_estandar(), 1.0)
    assert sin_nota.properties["estimated_thickness"] == pytest.approx(0.18)
    assert sin_nota.properties["estimated_length"] == pytest.approx(6.6)
    assert "espesor_fuente" not in sin_nota.properties
    assert avisos == []


def test_sin_nota_queda_lo_medido():
    muro = _muro("w3", 0.18, "outline", largo=6.6, centreline_length=6.435)
    (igual,), avisos = escribir_espesor_de_muros([muro], reglas_estandar(), 1.0)
    assert igual.properties == muro.properties
    assert avisos == []


def test_un_muro_de_concreto_no_toma_la_nota_de_block():
    muro = _muro("w4", 0.20, None, wall_kind="concreto")
    (igual,), avisos = escribir_espesor_de_muros([muro], _con_nota(), 1.0)
    assert igual.properties["estimated_thickness"] == 0.20
    assert avisos == []


def test_una_cota_que_no_es_el_muro_se_deja_y_el_aviso_pide_revisarla():
    # R277 (W31 de PRUEBA-1): la «36» es una cota del eje del muro a otra cosa, no su espesor; el
    # núcleo dibujado mide 15, lo de la nota. La cota se deja (asociarla bien es de E1), pero el
    # aviso no la da por buena: dice lo que mide el muro y pide revisarla.
    muro = _muro(
        "w5", 0.3598, "core", thickness_source="cota", estimated_thickness_geometry=0.15
    )
    (escrito,), (aviso,) = escribir_espesor_de_muros([muro], _con_nota(), 1.0)
    assert escrito.properties["estimated_thickness"] == pytest.approx(0.3598)
    assert "w5" in aviso
    dicho = (
        "revisa: la cota de 36 cm no es lo que mide el muro dibujado (15 cm, lo que dice la nota)"
    )
    assert dicho in aviso
    assert "manda" not in aviso


def test_una_cota_que_es_el_muro_dibujado_se_deja_y_el_aviso_no_se_contradice():
    # Un muro de 20 dibujado y acotado en 20 contra una nota de 15: la cota no está mal, el
    # desacuerdo es con la nota. El aviso no dice que la cota «no es lo que mide el muro».
    muro = _muro(
        "w5", 0.20, "core", thickness_source="cota", estimated_thickness_geometry=0.20
    )
    (escrito,), (aviso,) = escribir_espesor_de_muros([muro], _con_nota(), 1.0)
    assert escrito.properties["estimated_thickness"] == pytest.approx(0.20)
    dicho = (
        "la cota de 20 cm es lo que mide el muro dibujado; la nota dice 15: quedó la cota, "
        "revisa cuál vale"
    )
    assert dicho in aviso and "w5" in aviso
    assert "no es lo que mide" not in aviso


def test_una_cota_sin_geometria_se_compara_con_la_nota():
    muro = _muro("w5", 0.30, None, thickness_source="cota")
    (escrito,), (aviso,) = escribir_espesor_de_muros([muro], _con_nota(), 1.0)
    assert escrito.properties["estimated_thickness"] == pytest.approx(0.30)
    assert "revisa: la cota de 30 cm no es lo que dice la nota (15)" in aviso


# R276: la nota vale para un contorno de lo de la nota hasta dos aplanados más; el aplanado sólo
# engruesa: uno más delgado es otro muro (un tabique de 10), como uno más grueso. R286 (M8): el
# aplanado es el del detector, 2 cm por cara (+4 cm). R285: un núcleo ya no trae su aplanado; más
# grueso que la nota es otro muro (un block de 20) y se queda lo medido.
@pytest.mark.parametrize(
    ("espesor", "de", "toma", "dice"),
    [
        (0.10, "outline", False, "más delgado que la nota (15): no es el muro de la nota"),
        (0.135, "core", False, "más delgado que la nota (15): no es el muro de la nota"),
        (0.15, "core", True, None),
        (0.18, "outline", True, "el contorno incluye el aplanado"),
        (0.18, "core", False, "sin su aplanado, más grueso que la nota (15): no es el muro"),
        (0.19, "outline", True, "el contorno incluye el aplanado"),
        (0.20, "core", False, "sin su aplanado, más grueso que la nota (15): no es el muro"),
        (0.20, "outline", False, "más grueso que la nota (15) y dos aplanados: no es el muro"),
        (0.25, "core", False, "sin su aplanado, más grueso que la nota (15): no es el muro"),
        (0.25, "outline", False, "más grueso que la nota (15) y dos aplanados: no es el muro"),
    ],
)
def test_la_nota_vale_de_su_espesor_a_dos_aplanados_mas(espesor, de, toma, dice):
    muro = _muro("w9", espesor, de)
    (escrito,), avisos = escribir_espesor_de_muros([muro], _con_nota(), 1.0)
    esperado = 0.15 if toma else espesor
    assert escrito.properties["estimated_thickness"] == pytest.approx(esperado)
    assert (escrito.properties.get("espesor_fuente") == "nota") is toma
    if dice is None:
        assert avisos == []
    else:
        (aviso,) = avisos
        assert dice in aviso and "w9" in aviso
        if not toma:
            assert "se queda lo medido" in aviso


def test_las_notas_de_la_regla_las_lee_la_lectura_de_reglas_y_el_presupuesto(tmp_path):
    # De punta a punta: la nota del plano, la regla y el muro de 18 que la toma (variante 15).
    r = _reglas(tmp_path, PRUEBA_1)
    (escrito,), _ = escribir_espesor_de_muros([_muro("w6", 0.18, "outline")], r, 1.0)
    assert slug(firma(escrito, 1.0)) == "BLOCK-15"


def test_un_muro_dibujado_en_un_detalle_no_toma_la_nota():
    # La simbología y los detalles dibujan muros que no son de la obra: no se tocan ni se avisan.
    vistas = [
        ViewRegion(view_id="pb", title="PLANTA BAJA", kind=ViewKind.plan, anchor=(0, 0)),
        ViewRegion(view_id="det", title="DETALLES", kind=ViewKind.excluded, anchor=(0, 0)),
    ]
    seg = SheetSegmentation(views=vistas, is_segmented=True, assignment={"w7": "pb", "w8": "det"})
    en_planta, en_detalle = _muro("w7", 0.18, "outline"), _muro("w8", 0.086, "outline")
    (a, b), avisos = escribir_espesor_de_muros([en_planta, en_detalle], _con_nota(), 1.0, seg)
    assert a.properties["estimated_thickness"] == pytest.approx(0.15)
    assert b.properties == en_detalle.properties
    assert len(avisos) == 1 and "w8" not in avisos[0]


def test_el_detector_y_la_guarda_de_la_nota_usan_el_mismo_aplanado():
    # R286 (M8): un solo límite de aplanado, 2 cm por cara, para el detector y para el modelo.
    from klave_engine.detection.suite import DetectorSuiteConfig
    from klave_engine.detection.wall_detector import APLANADO_MAXIMO_M
    from klave_engine.dxf.units import DrawingUnits
    from klave_engine.estructura import modelo

    assert APLANADO_MAXIMO_M == pytest.approx(0.020)
    assert modelo._APLANADO_MAXIMO_M == APLANADO_MAXIMO_M
    for unidad, factor in (("m", 1.0), ("cm", 100.0), ("mm", 1000.0)):
        unidades = DrawingUnits(unit=unidad, source="declared", confidence=1.0)
        config = DetectorSuiteConfig.preset_for_units(unidades)
        assert config.wall.finish_max == pytest.approx(APLANADO_MAXIMO_M * factor)
