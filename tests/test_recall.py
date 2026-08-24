"""Medir cuánto ve el motor: por familia, con intervalo, y pesado por dinero."""

import json

from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.evals.recall import (
    ConteoDeObra,
    ConteoHumano,
    importe_por_familia,
    medir,
    plantilla_de_conteo,
    wilson,
)

from tests.test_hallazgos import _line, _report


def _det(i: int, familia: str):
    d = make_detection(
        f"d{i}", DetectionType.column_tag, f"K-{i}", (0, 0, 1, 1), 0.9, [], "m", [], {}
    )
    d.family = familia
    return d


def _conteo(**familias: int) -> ConteoDeObra:
    return ConteoDeObra(
        drawing_id="obra",
        contado_por="Diego",
        contado_en="2026-08-24",
        conteos=[ConteoHumano(familia=f, dibujados=n) for f, n in familias.items()],
    )


def test_el_recall_es_lo_encontrado_sobre_lo_dibujado():
    detections = [_det(i, "castillo") for i in range(8)]
    reporte = medir(_conteo(castillo=10), detections)
    familia = reporte.familias[0]
    assert familia.dibujados == 10 and familia.detectados == 8
    assert familia.recall == 0.8
    assert familia.faltantes == 2


def test_detectar_de_mas_no_infla_el_recall():
    """Contar doble entre vistas no es haber visto mejor: el recall se topa en
    1.0 y el excedente se anota aparte, porque también cuesta dinero."""
    detections = [_det(i, "castillo") for i in range(15)]
    familia = medir(_conteo(castillo=10), detections).familias[0]
    assert familia.recall == 1.0
    assert familia.sobrantes == 5


def test_una_familia_que_el_motor_no_ve_en_absoluto_sale_en_cero():
    """El caso más caro de descubrir: la familia entera invisible."""
    familia = medir(_conteo(escalera=3), []).familias[0]
    assert familia.detectados == 0 and familia.recall == 0.0


def test_el_intervalo_dice_cuando_la_muestra_es_chica():
    """Con 15 elementos, 0.87 no distingue 0.6 de 0.98, y el reporte no debe
    fingir que sí."""
    bajo, alto = wilson(13, 15)
    assert bajo < 0.7 and alto > 0.95  # ancho: la muestra no alcanza
    bajo_grande, alto_grande = wilson(1300, 1500)
    assert alto_grande - bajo_grande < 0.05  # con mil quinientos ya se estrecha
    assert wilson(0, 0) == (0.0, 0.0)


def test_el_recall_ponderado_pesa_el_dinero_no_las_piezas():
    """Cien ejes bien detectados no compensan diez trabes perdidas."""
    report = _report(
        [_line("EST-002", amount=900000.0), _line("CIM-002", amount=1000.0)]
    )
    detections = [_det(i, "trabe") for i in range(5)] + [
        _det(100 + i, "zapata") for i in range(10)
    ]
    reporte = medir(_conteo(trabe=10, zapata=10), detections, report)
    assert reporte.recall_global == 0.75  # 15 de 20 piezas
    # Las trabes valen $900k y las zapatas $1k: el número honesto está cerca
    # del recall de las trabes, no en medio.
    assert reporte.recall_ponderado < 0.55
    assert reporte.dinero_no_visto > 800000


def test_sin_reporte_de_costos_el_ponderado_cae_al_global():
    reporte = medir(_conteo(trabe=4), [_det(1, "trabe"), _det(2, "trabe")])
    assert reporte.recall_ponderado == reporte.recall_global == 0.5
    assert reporte.dinero_no_visto == 0.0


def test_el_importe_se_reparte_por_familia_desde_el_presupuesto():
    report = _report([_line("EST-002", amount=500.0), _line("EST-001", amount=300.0)])
    importes = importe_por_familia(report)
    assert importes["trabe"] == 500.0 and importes["castillo"] == 300.0
    assert importe_por_familia(None) == {}


def test_la_plantilla_sale_lista_para_llenarse_a_mano(tmp_path):
    plantilla = plantilla_de_conteo("obra", ["castillo", "trabe"])
    escrito = tmp_path / "obra.json"
    escrito.write_text(json.dumps(plantilla.a_json(), ensure_ascii=False), encoding="utf-8")
    otra_vez = ConteoDeObra.desde_json(escrito)
    assert [c.familia for c in otra_vez.conteos] == ["castillo", "trabe"]
    assert all(c.dibujados == 0 for c in otra_vez.conteos)
    assert "no haya detectado" in otra_vez.nota  # dice que hay que agregar familias
