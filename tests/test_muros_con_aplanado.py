"""Tarea 15f (R275): un muro dibujado con su aplanado es un muro.

PRUEBA-1 dibuja cada muro con dos contornos en la misma capa: el del block (15 cm) y, 15 mm
afuera por cada lado, el del aplanado (18 cm). La línea del aplanado no es una cara: es la
misma cara con su acabado. Se reconoce así: paralela a una cara del muro, en la misma capa, a
20 mm o menos hacia afuera y traslapada con ella en 90 % o más (del tramo más corto). El
espesor es el del núcleo; el largo, el eje del núcleo (cada junta en T una sola vez); los vanos,
los huecos que tienen las dos caras del núcleo. Una línea delgada en otra capa (un cancel, un
acabado) nunca se junta con el muro.
"""

import ezdxf
import pytest
from klave_engine.detection.wall_detector import WallDetectorConfig, detect_walls
from klave_engine.dxf.parser import DxfParser
from klave_engine.geometry.spatial_index import SpatialIndex

CONFIG = WallDetectorConfig(
    min_length=1.5, max_thickness=0.45, min_thickness=0.05, merge_gap=0.30,
    opening_gap_max=1.30, finish_max=0.020, face_tolerance=0.001,
)


def _muros(tmp_path, dibujar, config=CONFIG):
    doc = ezdxf.new("R2010")
    dibujar(doc.modelspace())
    ruta = tmp_path / "muros.dxf"
    doc.saveas(ruta)
    dibujo = DxfParser().parse_file(ruta)
    salida = detect_walls(dibujo.entities, SpatialIndex(dibujo.entities), config)
    return sorted(salida.detections, key=lambda d: (d.bbox[0], d.bbox[1])), dibujo.entities


def _h(msp, x0, x1, y, capa="A-WALL"):
    msp.add_line((x0, y), (x1, y), dxfattribs={"layer": capa})


def _v(msp, x, y0, y1, capa="A-WALL"):
    msp.add_line((x, y0), (x, y1), dxfattribs={"layer": capa})


def _muro_con_aplanado(msp, x0=0.0, x1=10.0, y=0.0, a=0.015, t=0.15, capa="A-WALL"):
    """Un muro horizontal suelto: el contorno del aplanado (t + 2a) y, a ``a`` adentro por cada
    lado y en cada punta, el del block (t)."""
    _h(msp, x0, x1, y, capa)
    _h(msp, x0, x1, y + t + 2 * a, capa)
    _h(msp, x0 + a, x1 - a, y + a, capa)
    _h(msp, x0 + a, x1 - a, y + a + t, capa)


def test_el_contorno_del_aplanado_no_es_una_cara(tmp_path):
    (muro,), _ = _muros(tmp_path, _muro_con_aplanado)
    p = muro.properties
    assert p["estimated_thickness"] == pytest.approx(0.15)
    assert p["thickness_from"] == "core"
    assert p["finish_thickness"] == pytest.approx(0.015)
    assert p["outline_thickness"] == pytest.approx(0.18)
    # El eje del núcleo: el block va de 0.015 a 9.985.
    assert p["estimated_length"] == pytest.approx(9.97)
    assert p["openings"] == []


def test_cada_linea_dibujada_dos_veces_cuenta_una_vez(tmp_path):
    # El bloque de Revit y el model space traen la misma línea: la copia exacta no es otro muro
    # ni alarga el que hay.
    def dibujar(msp):
        _muro_con_aplanado(msp)
        _muro_con_aplanado(msp)

    (muro,), _ = _muros(tmp_path, dibujar)
    assert muro.properties["estimated_thickness"] == pytest.approx(0.15)
    assert muro.properties["estimated_length"] == pytest.approx(9.97)
    assert muro.properties["openings"] == []


def test_un_muro_con_aplanado_y_una_puerta(tmp_path):
    # La puerta: el aplanado da vuelta al vano, así que el block se abre 15 mm más por cada lado
    # (0.93) que el acabado (0.90). El vano del block es el hueco de las dos caras del núcleo.
    def dibujar(msp):
        for y in (0.0, 0.18):
            _h(msp, 0.0, 4.015, y)
            _h(msp, 4.915, 10.0, y)
        for y in (0.015, 0.165):
            _h(msp, 0.015, 4.0, y)
            _h(msp, 4.93, 9.985, y)

    (muro,), _ = _muros(tmp_path, dibujar)
    p = muro.properties
    assert p["estimated_thickness"] == pytest.approx(0.15)
    assert p["openings"] == [pytest.approx(0.93)]
    assert p["opening_length"] == pytest.approx(0.93)
    assert p["estimated_length"] == pytest.approx(9.97)


def test_un_hueco_de_una_sola_cara_es_una_junta_no_un_vano(tmp_path):
    # Un muro que llega en T abre una cara del que lo recibe (15 cm), no las dos.
    def dibujar(msp):
        _h(msp, 0.0, 10.0, 0.0)
        _h(msp, 0.015, 9.985, 0.015)
        _h(msp, 0.015, 5.0, 0.165)
        _h(msp, 5.15, 9.985, 0.165)
        _h(msp, 0.0, 4.985, 0.18)
        _h(msp, 5.165, 10.0, 0.18)
        # El muro que llega: su núcleo entra hasta la cara del núcleo del otro.
        _v(msp, 5.0, 0.165, 4.985)
        _v(msp, 5.15, 0.165, 4.985)
        _v(msp, 4.985, 0.18, 5.0)
        _v(msp, 5.165, 0.18, 5.0)

    muros, _ = _muros(tmp_path, dibujar)
    horizontal, vertical = sorted(muros, key=lambda d: d.bbox[3] - d.bbox[1])
    assert horizontal.properties["openings"] == []
    # Cada junta en T una sola vez: el que recibe pasa de largo; el que llega para en su núcleo.
    assert horizontal.properties["estimated_length"] == pytest.approx(9.97)
    assert vertical.properties["estimated_length"] == pytest.approx(4.82)
    assert vertical.properties["estimated_thickness"] == pytest.approx(0.15)


def test_el_aplanado_de_un_solo_lado(tmp_path):
    # Una cara con aplanado y la otra sin él (W44 de PRUEBA-1): el núcleo sigue siendo de 15.
    def dibujar(msp):
        _h(msp, 0.0, 10.0, 0.0)
        _h(msp, 0.015, 9.985, 0.015)
        _h(msp, 0.015, 9.985, 0.165)

    (muro,), _ = _muros(tmp_path, dibujar)
    assert muro.properties["estimated_thickness"] == pytest.approx(0.15)
    assert muro.properties["thickness_from"] == "core"


@pytest.mark.parametrize(("a", "es_aplanado"), [(0.020, True), (0.021, False)])
def test_el_aplanado_esta_a_20_mm_o_menos(tmp_path, a, es_aplanado):
    (muro,), _ = _muros(tmp_path, lambda msp: _muro_con_aplanado(msp, a=a))
    if es_aplanado:
        assert muro.properties["thickness_from"] == "core"
        assert muro.properties["estimated_thickness"] == pytest.approx(0.15)
        assert muro.properties["finish_thickness"] == pytest.approx(a)
    else:
        assert "finish_thickness" not in muro.properties
        assert muro.properties.get("thickness_from") != "core"


@pytest.mark.parametrize(("inicio", "es_aplanado"), [(1.0, True), (1.1, False)])
def test_el_aplanado_traslapa_su_cara_en_90_por_ciento(tmp_path, inicio, es_aplanado):
    # El núcleo va de 0 a 10; el contorno corrido empieza en ``inicio`` y mide 10: traslapa
    # 9.0 (90 %) o 8.9 (89 %) del más corto.
    def dibujar(msp):
        _h(msp, 0.0, 10.0, 0.015)
        _h(msp, 0.0, 10.0, 0.165)
        _h(msp, inicio, inicio + 10.0, 0.0)
        _h(msp, inicio, inicio + 10.0, 0.18)

    muros, _ = _muros(tmp_path, dibujar)
    nucleos = [m for m in muros if m.properties.get("thickness_from") == "core"]
    if es_aplanado:
        (muro,) = muros
        assert nucleos == [muro]
        assert muro.properties["estimated_thickness"] == pytest.approx(0.15)
    else:
        assert nucleos == []


def test_una_linea_delgada_de_otra_capa_nunca_es_el_aplanado(tmp_path):
    # Un cancel o un acabado a 15 mm de la cara, en su propia capa: el muro no lo toma.
    def dibujar(msp):
        _h(msp, 0.0, 10.0, 0.0)
        _h(msp, 0.0, 10.0, 0.15)
        _h(msp, 0.0, 10.0, -0.015, capa="A-CANCELERIA")
        _h(msp, 0.0, 10.0, 0.17, capa="A-ACABADOS")

    (muro,), entidades = _muros(tmp_path, dibujar)
    ajenas = {e.entity_id for e in entidades if e.layer != "A-WALL"}
    assert not ajenas & set(muro.source_entities)
    assert muro.properties["estimated_thickness"] == pytest.approx(0.15)
    assert "finish_thickness" not in muro.properties


def test_una_linea_a_15_mm_en_otra_capa_de_muros_tampoco(tmp_path):
    # Aun en una capa que también es de muros, el aplanado tiene que estar en la capa del muro.
    def dibujar(msp):
        _h(msp, 0.0, 10.0, 0.0)
        _h(msp, 0.0, 10.0, 0.15)
        _h(msp, 0.0, 10.0, -0.015, capa="MUROS-ACABADO")

    muros, _ = _muros(tmp_path, dibujar)
    assert all("finish_thickness" not in m.properties for m in muros)


def test_un_muro_sin_aplanado_dice_el_eje_de_su_contorno(tmp_path):
    # Dibujado sólo con su contorno: el espesor es el medido y no cambia; su eje queda a la mano
    # (``centreline_length``) para quien sepa que el contorno incluye el aplanado.
    def dibujar(msp):
        _h(msp, 0.0, 6.45, 0.0)
        _h(msp, -0.15, 6.27, 0.18)

    (muro,), _ = _muros(tmp_path, dibujar)
    p = muro.properties
    assert p["estimated_thickness"] == pytest.approx(0.18)
    assert p["thickness_from"] == "outline"
    assert "finish_thickness" not in p
    assert p["centreline_length"] == pytest.approx(6.435)


# --- lo que hoy pasa con un elemento delgado de verdad en la MISMA capa (revisión de la 15f) ---
# En su misma capa y a 20 mm o menos, una línea que no es aplanado (una chapa de piedra, un
# rodapié dibujado en A-WALL) se lee como si lo fuera: el traslape del 90 % se mide contra el tramo
# MÁS CORTO, así que una línea de 3 m junto a un muro de 10 lo cumple. Estas pruebas fijan lo que
# hace hoy, no lo que debería: el dibujo no dice qué es esa línea.


def test_una_linea_delgada_afuera_en_la_misma_capa_se_lee_como_aplanado(tmp_path):
    # Afuera del muro: el núcleo sigue siendo el par verdadero (15), y el largo y los vanos se leen
    # de sus caras; sólo se le atribuye un aplanado que no es.
    def dibujar(msp):
        _h(msp, 0.0, 10.0, 0.0)
        _h(msp, 0.0, 10.0, 0.15)
        _h(msp, 2.0, 5.0, -0.015)  # 3 m en la misma capa, 15 mm afuera

    (muro,), _ = _muros(tmp_path, dibujar)
    p = muro.properties
    assert p["thickness_from"] == "core"
    assert p["estimated_thickness"] == pytest.approx(0.15)
    assert p["finish_thickness"] == pytest.approx(0.015)
    assert p["estimated_length"] == pytest.approx(10.0)


def test_una_linea_delgada_adentro_en_la_misma_capa_adelgaza_el_muro(tmp_path):
    # Adentro del muro (caras en 0, 0.135 y 0.15): la cara de 0.15 se toma por el aplanado de la
    # de 0.135 y el muro se lee de 13.5 cm. Es el patrón de W44 (aplanado de un solo lado): el
    # dibujo solo no los distingue. Con una nota de 15 el presupuesto no lo toma callado (R276:
    # más delgado que la nota, se queda lo medido y se avisa).
    def dibujar(msp):
        _h(msp, 0.0, 10.0, 0.0)
        _h(msp, 0.0, 10.0, 0.15)
        _h(msp, 0.0, 10.0, 0.135)

    (muro,), _ = _muros(tmp_path, dibujar)
    assert muro.properties["thickness_from"] == "core"
    assert muro.properties["estimated_thickness"] == pytest.approx(0.135)
