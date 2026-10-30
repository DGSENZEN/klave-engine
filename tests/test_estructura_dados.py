"""Tarea 15b: las etiquetas D-n se juntan con sus dados y la altura de cada dado sale de su corte.

Los casos son los de Marina, sintéticos (el plano no está en el repositorio): un dado D-1 de
55×55 con su etiqueta a 0.22 m de su contorno, en la misma capa EST-DADOS; una etiqueta a la misma
distancia de dos contornos; D-X dibujado dentro de D-4; el corte «D-1 / CORTE / Y-Y'» con su cota
vertical «100» y la planta del dado con su «55» al lado; el detalle «D-C» de una dala, escrito
«DC» en planta."""

from klave_engine.detection.footing_detector import FootingDetectorConfig, detect_footings
from klave_engine.detection.schedules import build_schedule_inventory
from klave_engine.detection.text_patterns import TextPatternConfig
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.estructura.definiciones import construir_definiciones
from klave_engine.geometry.spatial_index import SpatialIndex
from klave_engine.graph.evidence import EvidencePacket

C = TextPatternConfig()


def _ev(eid, bbox):
    return EvidencePacket(source="a.dxf", method="t", entity_ids=[eid], bbox=bbox, confidence=1.0)


def _contorno(eid, x0, y0, x1, y1, capa="EST-DADOS"):
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return NormalizedEntity(
        entity_id=eid, entity_type=EntityType.polyline, layer=capa, source_file="a.dxf",
        points=pts, bbox=(x0, y0, x1, y1), raw_handle=eid.upper(), properties={"closed": True},
        evidence=_ev(eid, (x0, y0, x1, y1)),
    )  # fmt: skip


def _texto(eid, valor, x, y, alto=0.1, capa="EST-DADOS"):
    """Un texto con su esquina inferior izquierda en (x, y)."""
    renglones = valor.split("\n")
    ancho = 0.9 * alto * max(len(r) for r in renglones)
    bbox = (x, y, x + ancho, y + alto * (1.7 * len(renglones) - 0.7))
    return NormalizedEntity(
        entity_id=eid, entity_type=EntityType.text, layer=capa, source_file="a.dxf",
        text=valor, bbox=bbox, raw_handle=eid.upper(), properties={"height": alto},
        evidence=_ev(eid, bbox),
    )  # fmt: skip


def _detectar(entidades):
    config = FootingDetectorConfig(
        min_area=0.55 * 0.55 - 1e-9, max_area=5.5 * 5.5, mark_search_radius=1.2,
        layer_mark_reach=0.6, semantic_authority_min=1, column_search_radius=2.0,
    )  # fmt: skip
    salida = detect_footings(entidades, SpatialIndex(entidades), None, config)
    return {d.source_entities[0]: d for d in salida.detections}


# ------------------------------------------------------------------ la etiqueta y su contorno


def test_la_etiqueta_d_n_se_junta_con_el_dado_que_rotula_en_su_capa():
    # D-1 (55×55) y su etiqueta 0.22 m debajo; D-4B (80×170) a 1 m, con la suya a 0.27 m.
    dados = _detectar([
        _contorno("d1", 0.0, 0.0, 0.55, 0.55),
        _texto("t1", "D-1", 0.1, -0.32),
        _contorno("d4b", 1.55, 0.0, 2.35, 1.70),
        _texto("t4b", "D-4B", 1.6, -0.37),
    ])  # fmt: skip
    assert dados["d1"].properties["mark"] == "D-1"
    assert dados["d4b"].properties["mark"] == "D-4B"
    # La etiqueta es de la colocación (como la de un castillo): ya no es una escritura suelta.
    assert "t1" in dados["d1"].source_entities and "t4b" in dados["d4b"].source_entities
    # La capa dice DADO: la familia la dice el plano, no el prefijo D- (R159).
    assert {d.properties.get("familia_de_capa") for d in dados.values()} == {"dado"}
    assert "etiquetas_disputadas" not in dados["d1"].properties


def test_una_etiqueta_d_n_en_otra_capa_no_rotula_ni_decide_la_familia():
    # El prefijo D- solo nunca decide (R159): una «D-1» fuera de la capa del contorno no se junta, y
    # un contorno de cimentación no es un dado.
    dados = _detectar([
        _contorno("z", 0.0, 0.0, 0.8, 0.8, capa="EST-CIMENTACION"),
        _texto("t", "D-1", 0.1, -0.3, capa="EST-CIMENTACION"),
        _contorno("d", 3.0, 0.0, 3.8, 0.8),
        _texto("u", "D-4", 3.1, -0.3, capa="EST-TEXTOS"),
    ])  # fmt: skip
    assert "mark" not in dados["z"].properties and "mark" not in dados["d"].properties
    assert "familia_de_capa" not in dados["z"].properties
    assert dados["d"].properties["familia_de_capa"] == "dado"


def test_una_etiqueta_lejos_de_todo_contorno_no_se_junta():
    dados = _detectar([_contorno("d", 0.0, 0.0, 0.8, 0.8), _texto("t", "D-4", 0.1, -0.9)])
    assert "mark" not in dados["d"].properties


def test_una_etiqueta_entre_dos_contornos_se_queda_en_duda_nombrando_los_dos():
    # La etiqueta queda a 0.2 m de los dos: la geometría no dice de cuál es.
    dados = _detectar([
        _contorno("a", 0.0, 0.0, 0.8, 0.8),
        _contorno("b", 1.25, 0.0, 2.05, 0.8),
        _texto("t", "D-4", 0.89, 0.35, alto=0.1),
    ])  # fmt: skip
    for clave in ("a", "b"):
        d = dados[clave]
        assert "mark" not in d.properties
        (disputa,) = d.properties["etiquetas_disputadas"]
        assert disputa["marca"] == "D-4" and disputa["entidad"] == "t"
        assert sorted(disputa["contornos"]) == ["A", "B"]


def test_dos_etiquetas_que_escogen_un_mismo_contorno_no_lo_rotulan():
    dados = _detectar([
        _contorno("d", 0.0, 0.0, 0.8, 0.8),
        _texto("t1", "D-4", 0.1, -0.3),
        _texto("t2", "D-5", 0.1, 0.95),
    ])  # fmt: skip
    d = dados["d"]
    assert "mark" not in d.properties
    assert sorted(x["marca"] for x in d.properties["etiquetas_disputadas"]) == ["D-4", "D-5"]


def test_d_x_dentro_de_d_4_no_se_decide_ni_se_cuenta_dos_veces():
    # Marina ES-000: D-4 (35521, 80×80) contiene a D-X (E2EC4, 45×45, comparten la arista
    # izquierda); «D-4» va 0.27 m debajo de D-4 y «D-X» a la izquierda, a la misma distancia de los
    # dos contornos. D-X es más chico que una zapata: no es una colocación.
    dados = _detectar([
        _contorno("d4", 0.0, 0.0, 0.8, 0.8),
        _contorno("dx", -6e-6, 0.1, 0.45, 0.55),  # como en Marina: 6e-6 fuera de la arista
        _texto("t4", "D-4", 0.63, -0.32),
        _texto("tx", "D-X", -0.6, 0.3),
    ])  # fmt: skip
    assert set(dados) == {"d4"}
    d4 = dados["d4"]
    assert d4.properties["mark"] == "D-4" and "tx" not in d4.source_entities
    (anidado,) = d4.properties["anidados"]
    assert anidado["contorno"] == "DX" and anidado["marcas"] == ["D-X"]
    (disputa,) = d4.properties["etiquetas_disputadas"]
    assert disputa["marca"] == "D-X" and sorted(disputa["contornos"]) == ["D4", "DX"]


# ------------------------------------------------------------------ la altura desde su corte


def _cota(eid, p, q, valor, medida, angulo, dimlfac=1.0):
    xs, ys = (p[0], q[0]), (p[1], q[1])
    bbox = (min(xs) - 0.4, min(ys), max(xs), max(ys))
    return NormalizedEntity(
        entity_id=eid, entity_type=EntityType.dimension, layer="COTAS-100", source_file="a.dxf",
        bbox=bbox, raw_handle=eid.upper(),
        properties={"display_text": f"{valor:g}", "display_value": float(valor),
                    "dimlfac": dimlfac, "measurement": medida, "dimtype": 0,
                    "angle": angulo, "measured_segment": [list(p), list(q)]},
        evidence=_ev(eid, bbox),
    )  # fmt: skip


def _bloque_de_dado(n, x, marcas="D-1", titulo="DADO D-1", altura=100, con_planta=True):
    """Como ES-005: arriba la planta del dado («D-1 / PLANTA», su lado «55» en una cota vertical),
    abajo su corte («D-1 / CORTE / Y-Y'», la cota vertical de su altura —«100», dibujada a otra
    escala: mide 4.96— y la de 20 del firme), y bajo el corte el título del bloque y su nota."""
    ents = []
    if con_planta:
        ents += [
            _texto(f"{n}pl", f"{marcas}\nPLANTA", x + 0.2, 9.6, alto=0.115, capa="T"),
            _cota(f"{n}c55", (x - 0.3, 10.3), (x - 0.3, 13.0), 55, 2.7, 90.0),
        ]
    ents += [
        _cota(f"{n}alt", (x - 0.4, 7.4), (x - 0.4, 2.44), altura, 4.96, 90.0),
        _cota(f"{n}c20", (x + 3.8, 7.4), (x + 3.8, 6.34), 20, 1.06, 90.0),
        _texto(f"{n}co", f"{marcas}\nCORTE\nY-Y'" if marcas else "CORTE\nY-Y'", x + 1.5, 0.0,
               alto=0.115, capa="ESTRUCTURAL"),
    ]
    if titulo:
        ents.append(_texto(f"{n}ti", titulo, x + 1.0, -0.9, alto=0.18, capa="TITULOS"))
    ents.append(_texto(f"{n}no", "ACOTACIONES EN CMS, SIN ESCALA", x + 0.5, -1.3, alto=0.12))
    return ents


def _altura(inv, marca):
    return [s for s in inv.specs if s.mark == marca and s.length_m is not None]


def test_la_altura_de_un_dado_es_la_cota_de_su_corte_no_el_lado_de_su_planta():
    inv = build_schedule_inventory(_bloque_de_dado("a", 0.0), C, unit_to_m=1.0)
    (lectura,) = _altura(inv, "D-1")
    assert lectura.length_m == 1.0  # «100» cm: el texto de la cota, no lo que mide (4.96)
    assert lectura.family == "dado" and not lectura.familia_supuesta
    assert lectura.source == "detalle" and "longitud" in lectura.campos_con_texto
    assert "aalt" in lectura.entidades and "ac55" not in lectura.entidades
    assert "100" in lectura.source_text and "CORTE" in lectura.source_text.upper()


def test_un_corte_de_varias_marcas_da_su_altura_a_cada_una():
    ents = _bloque_de_dado("a", 0.0, marcas="D-1 Y D-2", titulo="DADO D-1 Y D-2", altura=120)
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0)
    assert [s.length_m for s in _altura(inv, "D-1")] == [1.2]
    assert [s.length_m for s in _altura(inv, "D-2")] == [1.2]


def test_un_corte_cuyo_titulo_no_nombra_marca_no_atribuye_altura():
    ents = _bloque_de_dado("a", 0.0, marcas="", titulo="DADO", con_planta=False)
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0)
    assert not [s for s in inv.specs if s.length_m is not None]


def test_sin_la_palabra_dado_el_prefijo_no_hace_dado_al_corte():
    # R159: «D-1 / CORTE» sin un título que diga DADO (o ZAPATA) no se lee como dado.
    inv = build_schedule_inventory(_bloque_de_dado("a", 0.0, titulo=None), C, unit_to_m=1.0)
    assert not _altura(inv, "D-1")


def test_cada_corte_toma_las_cotas_de_su_bloque():
    ents = _bloque_de_dado("a", 0.0) + _bloque_de_dado(
        "b", 9.0, marcas="D-4B", titulo="DADO D-4B", altura=140
    )
    inv = build_schedule_inventory(ents, C, unit_to_m=1.0)
    assert [s.length_m for s in _altura(inv, "D-1")] == [1.0]
    assert [s.length_m for s in _altura(inv, "D-4B")] == [1.4]


# ------------------------------------------------------------------ D-C es la dala DC (R259)


def _detalle_d_c(titulo="DALA"):
    """Como ES-200 AF02D: «D-C» sobre su sección de 30×20 (cotas abajo y a la izquierda), «6#3» y
    «E#2@15» bajo la sección, el título del bloque y su nota."""
    ents = [
        _texto("dc", "D-C", 1.0, 2.25, alto=0.13, capa="DETALLES"),
        _contorno("sec", 0.45, 1.0, 2.25, 2.15, capa="DETALLES"),
        _cota("c30", (0.45, 0.95), (2.25, 0.95), 30, 1.8, 0.0, dimlfac=100.0),
        _cota("c20", (0.40, 1.0), (0.40, 2.15), 20, 1.14, 90.0),
        _texto("r1", "6#3", 1.1, 0.5, capa="DETALLES"),
        _texto("r2", "E#2@15", 1.0, 0.32, capa="DETALLES"),
        _texto("no", "ACOTACIONES EN CMS, SIN ESCALA", 0.4, -0.35, capa="DETALLES"),
    ]
    if titulo:
        ents.append(_texto("ti", titulo, 1.0, 0.0, alto=0.16, capa="DETALLES"))
    return ents


def test_d_c_define_a_la_dala_dc_porque_su_titulo_dice_dala():
    inv = build_schedule_inventory(_detalle_d_c(), C, unit_to_m=1.0)
    lecturas = [s for s in inv.specs if s.mark == "DC"]
    assert lecturas and all(s.family == "dala" and not s.familia_supuesta for s in lecturas)
    assert all(s.source == "detalle" for s in lecturas)
    assert any("D-C" in s.source_text for s in lecturas) and "dc" in inv.titulos_de_detalle
    # Lo que el detalle escribe ya tiene dueño.
    assert not [r for r in inv.rechazos if r.entidad_id in ("r1", "r2")]
    por_marca, _ = construir_definiciones(inv, C)
    dc = por_marca["DC"]
    assert dc.familia == "dala"
    assert dc.seccion_cm is not None and dc.seccion_cm.valor == (30, 20)
    assert dc.seccion_cm.fuente == "detalle"
    assert dc.longitudinales is not None
    assert [(g.cantidad, g.numero) for g in dc.longitudinales.valor] == [(6, "3")]
    assert dc.estribos is not None
    (juego,) = dc.estribos.valor
    assert juego.numero == "2" and juego.zonas[0].separacion_m == 0.15
    assert "D-C" not in por_marca


def test_d_c_no_es_dc_si_su_titulo_no_dice_dala():
    for titulo in ("DADO", None):
        inv = build_schedule_inventory(_detalle_d_c(titulo), C, unit_to_m=1.0)
        assert not [s for s in inv.specs if s.mark == "DC"], titulo


# ------------------------------------------------------------------ CIM-002 con su altura


def _zapata(det_id, area, **props):
    from klave_engine.detection.results import DetectionType, make_detection

    lado = area**0.5
    d = make_detection(
        det_id, DetectionType.footing, det_id, (0, 0, lado, lado), 0.9, [f"c_{det_id}"],
        "footing_closed_rectangular_polyline", [], {"estimated_area": area, **props}, "a.dxf",
    )  # fmt: skip
    d.family = "zapata"
    return d


def _elemento_dado(det_id, altura):
    from klave_engine.estructura.elementos import Colocacion, Elemento

    return Elemento(
        element_id=f"el_{det_id}", detection_id=det_id, marca="D-1", familia="dado",
        hoja="ES-000", definicion="marca", altura_m=altura, colocacion=Colocacion(),
    )  # fmt: skip


def _cim_002(detecciones, elementos):
    from klave_engine.costing.models import CostingConfig
    from klave_engine.costing.report import generate_cost_report
    from klave_engine.dxf.units import DrawingUnits
    from klave_engine.estructura.reglas import reglas_estandar

    report = generate_cost_report(
        "p", detecciones, DrawingUnits(unit="m", source="declared", confidence=1.0),
        CostingConfig(), None, None,
        estructura={"reglas": reglas_estandar().model_dump(mode="json"),
                    "elementos": [e.model_dump(mode="json") for e in elementos]},
    )  # fmt: skip
    return next(line for line in report.boq.lines if line.concept_code == "CIM-002")


def test_cim_002_mide_cada_dado_con_la_altura_que_acota_su_corte():
    from klave_engine.costing.models import CostingAssumptions
    from klave_engine.estructura.dato import Dato
    from klave_engine.estructura.modelo import escribir_en_detecciones

    del_corte = Dato(valor=1.4, fuente="detalle", hoja="ES-006", texto="D-4B · altura 140 cm")
    supuesta = CostingAssumptions().footing_depth_m
    supuesto = Dato(valor=supuesta, fuente="supuesto", texto="altura supuesta")
    dets = [_zapata("d1", 1.36), _zapata("d2", 0.64), _zapata("d3", 0.81)]
    els = [_elemento_dado("d1", del_corte), _elemento_dado("d2", supuesto)]  # d3: sin elemento
    linea = _cim_002(dets, els)
    assert abs(linea.quantity - (1.36 * 1.4 + 0.64 * supuesta + 0.81 * supuesta)) < 1e-6
    # La escritura es pura (R235): escrita dos veces da lo mismo, y sin el modelo se deshace.
    una, escritas = escribir_en_detecciones(dets, els, 1.0)
    assert [(e.detection_id, e.campo, e.despues) for e in escritas] == [("d1", "peralte", "140 cm")]
    assert una[0].properties["peralte_cm"] == 140 and "peralte_cm" not in una[1].properties
    dos, _ = escribir_en_detecciones(una, els, 1.0)
    assert dos[0].properties == una[0].properties
    sin, _ = escribir_en_detecciones(una, [], 1.0)
    assert sin[0].properties == dets[0].properties
