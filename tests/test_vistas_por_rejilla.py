"""Tarea 15c: una etiqueta es de una sola vista, la que dibuja la rejilla de ejes que la contiene.

PRUEBA-1 (una hoja con cuatro plantas, sin marcos) ponía las vistas por cercanía a su título: el
título de PLANTA ALTA está debajo de su planta, junto a la esquina de arriba de la AZOTEA, y cuatro
castillos de la azotea quedaban en la planta alta (siete del muro poniente de PLANTA BAJA en la
simbología, cuatro de la cimentación en el armado de castillos). El dibujo de cada planta es su
rejilla de ejes: lo que está dentro de la rejilla de una sola planta es de esa planta.
"""

import ezdxf
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.views import VISTA_EN_DUDA, ViewKind, segment_views
from klave_engine.dxf.parser import DxfParser


def _entities(tmp_path, build):
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    for i in range(8):
        msp.add_text("nota chica", height=0.2).set_placement((i - 40, -40))
    msp.add_text("PLANTA ALTA", height=1.0).set_placement((0, 0))
    msp.add_text("AZOTEA", height=1.0).set_placement((22, -22))
    build(msp)
    path = tmp_path / "rejillas.dxf"
    doc.saveas(path)
    return DxfParser().parse_file(path).entities


def _eje(detection_id, x0, y0, x1, y1):
    eje = "horizontal" if abs(y1 - y0) < abs(x1 - x0) else "vertical"
    return make_detection(
        detection_id, DetectionType.grid_line, detection_id, (x0, y0, x1, y1), 0.9, [], "m", [],
        {"axis": eje},
    )  # fmt: skip


def _rejilla(prefijo, x0, y0, x1, y1):
    """Tres ejes verticales y tres horizontales que se cruzan: la rejilla de una planta."""
    ejes = []
    for i in range(3):
        x = x0 + (x1 - x0) * (i + 1) / 4
        y = y0 + (y1 - y0) * (i + 1) / 4
        ejes.append(_eje(f"{prefijo}_v{i}", x, y0, x, y1))
        ejes.append(_eje(f"{prefijo}_h{i}", x0, y, x1, y))
    return ejes


def _k(detection_id, x, y):
    caja = (x - 0.1, y - 0.1, x + 0.1, y + 0.1)
    return make_detection(detection_id, DetectionType.column_tag, "K-1", caja, 0.9, [], "m", [])


def _muro(msp, puntos):
    """Un muro en trazos de 1 m: ninguno tan largo como para unir dos dibujos de la hoja."""
    for (x0, y0), (x1, y1) in zip(puntos, puntos[1:], strict=False):
        n = max(1, round(max(abs(x1 - x0), abs(y1 - y0))))
        for i in range(n):
            a = (x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n)
            b = (x0 + (x1 - x0) * (i + 1) / n, y0 + (y1 - y0) * (i + 1) / n)
            msp.add_line(a, b, dxfattribs={"layer": "MUROS"})


def _titulo_de(seg, detection_id):
    return {v.view_id: v.title for v in seg.views}[seg.assignment[detection_id]]


def test_a_tag_inside_one_views_grid_is_that_views_even_if_another_title_is_nearer(tmp_path):
    # La forma de PRUEBA-1: el título de PLANTA ALTA está debajo de su planta y junto a la esquina
    # de arriba de la rejilla de la AZOTEA. El castillo de esa esquina está más cerca del título de
    # la planta alta (12 contra 21: no es un casi empate), pero lo dibuja la rejilla de la azotea.
    entities = _entities(tmp_path, lambda msp: None)
    dets = [
        *_rejilla("pa", -2, 2, 12, 16),
        *_rejilla("az", 14, -20, 30, -1),
        _k("esquina", 15.0, -2.0),
        _k("pa", 5.0, 10.0),
        _k("fuera", 40.0, 5.0),
    ]
    seg = segment_views(entities, dets, [])
    assert _titulo_de(seg, "esquina") == "AZOTEA"
    assert _titulo_de(seg, "pa") == "PLANTA ALTA"
    # Fuera de toda rejilla, la vista sigue siendo la del título más cercano.
    assert _titulo_de(seg, "fuera") == "AZOTEA"
    # Los ejes de cada rejilla son de su planta.
    assert {_titulo_de(seg, d.detection_id) for d in dets if d.detection_id.startswith("az_")} == {
        "AZOTEA"
    }
    # Cada detección está en una sola vista.
    ids = [i for v in seg.views for i in v.detection_ids]
    assert sorted(ids) == sorted(d.detection_id for d in dets)
    assert seg.vistas_dudosas == {}


def _traslapadas(muro):
    def build(msp):
        if muro:
            # El muro de la azotea pasa por la esquina donde las dos rejillas se traslapan.
            _muro(msp, [(15, 3), (15, -10), (25, -10)])

    return build


def test_a_tag_where_two_grids_overlap_is_placed_by_its_drawing(tmp_path):
    # Las rejillas de las dos plantas se traslapan en (14..16, 2..4). El castillo de ahí está en
    # el muro de la azotea, el mismo que tiene castillos que sólo la rejilla de la azotea contiene:
    # es de la azotea.
    entities = _entities(tmp_path, _traslapadas(True))
    dets = [
        *_rejilla("pa", -2, 2, 16, 16),
        *_rejilla("az", 14, -20, 30, 4),
        _k("t", 15.0, 3.0),
        _k("az1", 15.0, -5.0),
        _k("az2", 20.0, -10.0),
    ]
    seg = segment_views(entities, dets, [])
    assert _titulo_de(seg, "t") == "AZOTEA"
    assert "t" not in seg.vistas_dudosas


def test_a_tag_no_drawing_can_place_is_a_duda_in_neither_planta(tmp_path):
    # Sin dibujo que lo diga, el castillo del traslape es una duda: se cuenta una vez, en una
    # región aparte que no es planta (ninguna de las dos lo cobra hasta que se decida), y lo dice.
    entities = _entities(tmp_path, _traslapadas(False))
    dets = [
        *_rejilla("pa", -2, 2, 16, 16),
        *_rejilla("az", 14, -20, 30, 4),
        _k("t", 15.0, 3.0),
        _k("az1", 15.0, -5.0),
    ]
    seg = segment_views(entities, dets, [])
    assert seg.assignment["t"] == VISTA_EN_DUDA
    duda = next(v for v in seg.views if v.view_id == VISTA_EN_DUDA)
    assert duda.kind == ViewKind.excluded
    assert duda.detection_ids == ["t"]
    assert all("t" not in v.detection_ids for v in seg.views if v.view_id != VISTA_EN_DUDA)
    assert seg.vistas_dudosas["t"] == (
        "vista en duda: está dentro de la rejilla de «AZOTEA» y de la de «PLANTA ALTA», y su "
        "dibujo no dice de cuál es (0 contra 0); no se cuenta en ninguna de las dos hasta que se "
        "decida"
    )
    assert "1 detecciones en vista en duda" in seg.notes


def test_a_grid_about_as_near_two_titles_places_nothing(tmp_path):
    # Una rejilla que no es claramente de un título (el segundo no está ni al doble de lejos) no
    # dice de qué planta es lo que contiene: la vista sigue siendo la del título más cercano. La
    # rejilla está a 7.0 del título de PLANTA ALTA y a 8.4 del de AZOTEA; el castillo de su
    # esquina, a 21.4 y a 9.1.
    entities = _entities(tmp_path, lambda msp: None)
    dets = [*_rejilla("medio", 6, -14, 20, -6), _k("k", 19.5, -13.5)]
    seg = segment_views(entities, dets, [])
    assert _titulo_de(seg, "k") == "AZOTEA"


# ------------------------------------------------- la duda en la lectura estructural (no cae)


def _seg_con_duda(k, aviso):
    from klave_engine.detection.views import SheetSegmentation, ViewRegion

    vistas = [
        ViewRegion(view_id=v, title=t, kind=ViewKind.plan, level_key=v, anchor=(0, 0))
        for v, t in (("v_pa", "PLANTA ALTA"), ("v_az", "AZOTEA"))
    ] + [
        ViewRegion(view_id=VISTA_EN_DUDA, title="En duda entre dos plantas",
                   kind=ViewKind.excluded, anchor=(0, 0), detection_ids=[k.detection_id])
    ]  # fmt: skip
    return SheetSegmentation(
        views=vistas,
        assignment={k.detection_id: VISTA_EN_DUDA},
        is_segmented=True,
        vistas_dudosas={k.detection_id: aviso},
    )


_AVISO = (
    "vista en duda: está dentro de la rejilla de «AZOTEA» y de la de «PLANTA ALTA», y su dibujo "
    "no dice de cuál es (0 contra 0); no se cuenta en ninguna de las dos hasta que se decida"
)


def _castillo():
    k = make_detection(
        "k", DetectionType.column_tag, "K-1", (0, 0, 0.2, 0.1), 0.9, ["ent_k"], "m", [], {}, "a.dxf"
    )
    k.mark, k.family = "K-1", "castillo"
    return k


def test_a_duda_placement_is_no_element_and_says_why():
    from klave_engine.estructura.elementos import excluidas

    k = _castillo()
    (x,) = excluidas([k], _seg_con_duda(k, _AVISO))
    assert x.motivo == "vista_en_duda"
    assert x.texto == _AVISO


def test_a_duda_placement_is_a_check_7_duda():
    from klave_engine.detection.schedules import ScheduleInventory
    from klave_engine.estructura.reglas import reglas_estandar
    from klave_engine.estructura.verificaciones import verificar

    k = _castillo()
    v = verificar(
        {}, {}, [], reglas_estandar(), ScheduleInventory(), [], [k], _seg_con_duda(k, _AVISO),
        frames=[],
    )  # fmt: skip
    (h,) = [x for x in v if x.numero == 7 and "vista en duda" in x.mensaje]
    assert h.severidad == "duda"
    assert h.marcas == ["K-1"]
    assert "no se cuenta en ninguna" in h.mensaje


def test_an_entity_inside_one_grid_is_that_plantas_even_where_the_view_boxes_overlap(tmp_path):
    # Las cajas de las vistas (la unión de sus detecciones) pueden traslaparse: la de PLANTA ALTA
    # de PRUEBA-1 llega a la esquina de arriba de la AZOTEA (un corte de trabe junto a ella). Lo
    # que busca su planta por punto (un texto, un muro achurado) toma también la de su rejilla.
    from klave_engine.estructura.verificaciones import _Contexto, _vista_de

    def build(msp):
        msp.add_text("MC-1", height=0.2).set_placement((14.3, -8.1))

    entities = _entities(tmp_path, build)
    largo = make_detection(
        "pa_lejos", DetectionType.wall, "W1", (10.0, -8.5, 15.0, -7.5), 0.9, [], "m", []
    )
    dets = [*_rejilla("pa", -2, 2, 12, 16), *_rejilla("az", 14, -20, 30, -1), largo]
    seg = segment_views(entities, dets, [])
    assert sorted(t for _c, t in seg.rejillas) == sorted(
        v.view_id for v in seg.views if v.title in ("AZOTEA", "PLANTA ALTA")
    )
    pa = next(v for v in seg.views if v.title == "PLANTA ALTA")
    az = next(v for v in seg.views if v.title == "AZOTEA")
    # El muro centrado en (12.5, −8) está fuera de toda rejilla y más cerca de PLANTA ALTA, y
    # llega hasta x 15: la caja de esa vista entra en la rejilla de la azotea, y PLANTA ALTA va
    # antes en la lista de vistas.
    assert seg.assignment["pa_lejos"] == pa.view_id
    assert pa.bbox is not None and pa.bbox[2] == 15.0 and pa.bbox[1] == -8.5
    texto = next(e for e in entities if e.text == "MC-1")
    assert seg.vista_por_rejilla((14.5, -8.0)) == az.view_id
    ctx = _Contexto(
        por_marca={}, por_familia={}, elementos=[], reglas=None, inv=None,  # type: ignore[arg-type]
        entidades={texto.entity_id: texto}, detections=dets, segmentation=seg, frames=[],
        config=None, anclaje_m=0.0, desperdicio=0.0,  # type: ignore[arg-type]
    )  # fmt: skip
    assert _vista_de(ctx, texto) == az.view_id
