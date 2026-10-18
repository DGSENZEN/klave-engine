"""Tarea 10: el acero de cada elemento desde su armado estructurado — grupos de varillas, juegos
de estribos por forma, ganchos de 10Ø, recubrimiento por familia y por hoja, estribos acomodados
por zona — y la etapa de acero que lo lee, sin perder nunca un concepto en silencio (R148a)."""

import math
import re
import subprocess
import sys

import pytest
from klave_engine.costing.models import BillOfQuantities, BoqLine, QuantityKind
from klave_engine.costing.steel import BAR_KG_PER_M, compute_steel
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.estructura.acero import (
    AceroElemento,
    acero_elemento,
    diametro_m,
    extremos_supuesto_m,
    fila_de_varilla,
    gancho_m,
    longitud_pieza_m,
    posiciones,
    sin_acero,
)
from klave_engine.estructura.armado import Zona, parsear_armado
from klave_engine.estructura.dato import Dato
from klave_engine.estructura.elementos import Elemento
from klave_engine.estructura.reglas import TABLA_ESTANDAR, FilaVarilla, reglas_estandar


def _reglas_marina():
    """Las del plan (Tarea 5): 135° + 10Ø, recubrimiento de columna 0.05 y de castillo 0.03."""
    reglas = reglas_estandar()
    cubre = dict(reglas.recubrimiento_m)
    cubre["columna"] = Dato(valor=0.05, fuente="nota", hoja="ES-000", texto="5.0 CM EN COLUMNAS")
    cubre["castillo"] = Dato(valor=0.03, fuente="nota", hoja="ES-000",
                             texto="3.0 CM LIBRES EN CASTILLOS")  # fmt: skip
    return reglas.model_copy(update={"recubrimiento_m": cubre})


R = _reglas_marina()


def _elemento(
    marca, familia, seccion, largo, longitudinales, estribos, cover, *, hoja="ES-000",
    det_id=None, fuente_seccion="detalle", texto_seccion=None, fuente_largo="nota",
):  # fmt: skip
    armado = parsear_armado(longitudinales + ([estribos] if estribos else []), familia)
    assert not armado.avisos, armado.avisos
    largo_dato = None if largo is None else Dato(valor=largo, fuente=fuente_largo, hoja=hoja)
    con_altura = familia in ("castillo", "columna")
    return Elemento(
        element_id=f"e-{det_id or marca}",
        detection_id=det_id or f"d-{marca}",
        marca=marca,
        familia=familia,
        hoja=hoja,
        definicion="marca",
        seccion_cm=None
        if seccion is None
        else Dato(
            valor=seccion,
            fuente=fuente_seccion,
            hoja=hoja,
            texto=texto_seccion or f"{marca} {seccion[0]}x{seccion[1]}",
        ),  # fmt: skip
        altura_m=largo_dato if con_altura else None,
        longitud_m=None if con_altura else largo_dato,
        longitudinales=Dato(
            valor=armado.longitudinales, fuente="detalle", hoja=hoja, texto=" ".join(longitudinales)
        )  # fmt: skip
        if longitudinales
        else None,
        estribos=Dato(valor=armado.estribos, fuente="detalle", hoja=hoja, texto=estribos)
        if estribos
        else None,
        recubrimiento_m=Dato(valor=cover, fuente="nota", hoja=hoja),
    )


def _line(code, ids, raw=1.0):
    return BoqLine(
        concept_code=code, description=code, unit="M3", quantity=1.0, unit_price=1.0,
        amount=1.0, phase="Estructura", raw_quantity=raw, raw_kind=QuantityKind.COUNT,
        source_detection_count=len(ids), source_detections=ids, confidence=0.9,
    )  # fmt: skip


def _det(det_id, marca, tipo=DetectionType.column_tag, **props):
    return make_detection(det_id, tipo, marca, (0, 0, 1, 1), 0.9, [], "m", [], props)


def _estructura(*elementos, reglas=R):
    return {"reglas": reglas.model_dump(mode="json"),
            "elementos": [e.model_dump(mode="json") for e in elementos]}  # fmt: skip


def _boq_with_c1():
    c1 = _det("c1", "C-1")
    return BillOfQuantities(project_id="p", lines=[_line("EST-001", ["c1"])]), [c1]


def _c1():
    return _elemento("C-1", "columna", (45, 45), 3.10, ["8#8"], "2E#3EXT@10 CENTRO@20", 0.05,
                     det_id="c1")  # fmt: skip


def _estructura_c1():
    return _estructura(_c1())


def _old_specs(rebar="8#8", stirrups="2E#3@15"):
    return {"by_mark": {"C-1": {"rebar": rebar, "stirrups": stirrups, "section_cm": [45, 45]}}}


# ----------------------------------------------------------------------- el plan (brief)


def test_hooks():
    assert gancho_m("3", R, "estribo") == pytest.approx(0.20)  # 10 × 0.009525 → 0.10, × 2
    assert gancho_m("2", R, "estribo") == pytest.approx(0.14)
    assert gancho_m("4", R, "estribo") == pytest.approx(0.26)
    assert diametro_m("3") == pytest.approx(0.009525)


def test_piece_lengths_c1():
    assert longitud_pieza_m("perimetral", 0.45, 0.45, 0.05, "3", R, 8) == pytest.approx(1.60)
    assert longitud_pieza_m("rombo", 0.45, 0.45, 0.05, "3", R, 8) == pytest.approx(
        1.18995, abs=1e-4
    )
    assert longitud_pieza_m("grapa", 0.15, 0.30, 0.03, "3", R, 6) == pytest.approx(0.29)
    # interior: 2(h−2r) + 2(b−2r)/3 + gancho
    assert longitud_pieza_m("interior", 0.30, 0.60, 0.05, "3", R, 12) == pytest.approx(
        2 * 0.50 + 2 * 0.20 / 3 + 0.20
    )
    assert longitud_pieza_m("liga", 0.20, 0.40, 0.05, "2", R, 4) == pytest.approx(0.10 + 0.14)


def test_positions_laid_out():
    # R9: la separación nunca pasa de s (ceil); el plan decía 20 en el segundo caso.
    z = [Zona(tramo="extremos", separacion_m=0.10), Zona(tramo="centro", separacion_m=0.20)]
    assert extremos_supuesto_m(0.45, 0.45, 3.10) == pytest.approx(0.60)
    assert posiciones(3.10, z, None, 0.60) == 21  # 6 + 6 at ends (first at s/2), 9 between
    assert posiciones(3.10, [Zona(tramo="todo", separacion_m=0.15)], None, 0.0) == 21
    assert posiciones(4.00, [Zona(tramo="todo", separacion_m=0.15)], 0.06, 0.0) == 27


def test_c1_element_kg():
    a = acero_elemento(_c1(), R, anclaje_m=0.40)
    assert isinstance(a, AceroElemento)
    assert a.kg_por_numero["8"] == pytest.approx(8 * 3.50 * 3.973, rel=1e-6)  # 111.244
    assert a.kg_por_numero["3"] == pytest.approx(21 * (1.60 + 1.18995) * 0.560, rel=1e-4)
    assert any("rombo" in s and "supuesto" in s for s in a.supuestos)
    assert any("extremos 0.60 m" in s for s in a.supuestos)
    assert any("primer estribo" in s and "supuesto" in s for s in a.supuestos)


def test_steel_stage_uses_elements_and_falls_back():
    boq, dets = _boq_with_c1()
    with_model = compute_steel(boq, dets, None, None, 1.0, 2.7, estructura=_estructura_c1())
    line = next(x for x in with_model.lines if x.concept_code == "ACE-001")
    assert line.quantity == pytest.approx((111.244 + 32.810) * 1.05, rel=1e-3)
    assert any("2E#3 EXT@10 CENTRO@20" in n for n in line.notes)
    old = compute_steel(boq, dets, _old_specs(), None, 1.0, 2.7)  # no estructura: today's path
    assert old.lines and old.lines[0].concept_code == "ACE-001"


# ------------------------------------------------------------------ más allá del plan


def test_old_path_reads_canonical_strings_it_used_to_read():
    # Sin estructura, los textos canónicos («4#5+2#4», «2E#3@15», «EYG#3@15») se leen con
    # parsear_armado: ningún armado que antes se leía se pierde callado.
    boq, dets = _boq_with_c1()
    old = compute_steel(boq, dets, _old_specs("4#5+2#4", "2E#3@15"), None, 1.0, 3.0)
    line = next(x for x in old.lines if x.concept_code == "ACE-001")
    assert any("4#5+2#4" in n and "2E#3@15" in n for n in line.notes), line.notes
    assert not any("Armado supuesto" in n for n in line.notes)
    longitudinal = (4 * 1.552 + 2 * 0.994) * (3.0 + 0.40)
    perimeter = 2 * ((0.45 - 0.05) + (0.45 - 0.05)) + 0.075
    stirrups = 2 * (math.floor(3.0 / 0.15) + 1) * perimeter * 0.560
    assert line.quantity == pytest.approx((longitudinal + stirrups) * 1.05, abs=0.01)
    eyg = compute_steel(boq, dets, _old_specs("6#4", "EYG#3@15"), None, 1.0, 3.0)
    assert any("6#4 E#3@15" in n for n in eyg.lines[0].notes), eyg.lines[0].notes
    # un estribo suelto «#3@15», como lo guardaban las corridas viejas, sigue leyéndose
    bare = compute_steel(boq, dets, _old_specs("8#8", "#3@15"), None, 1.0, 3.0)
    assert any("8#8 E#3@15" in n for n in bare.lines[0].notes)
    # y uno por zonas sin su «E» («#3EXT@10 CENTRO@20») también: se lee como «E#3EXT@10 …»
    zonas = compute_steel(boq, dets, _old_specs("8#8", "#3EXT@10 CENTRO@20"), None, 1.0, 3.0)
    assert any("8#8 E#3 EXT@10 CENTRO@20" in n for n in zonas.lines[0].notes), zonas.lines[0].notes
    assert not any("Armado supuesto" in n for n in zonas.lines[0].notes)


def test_dalas_and_zapatas_read_canonical_strings():
    w = _det("w1", "W1", DetectionType.wall)
    z = _det("f1", "Z-1", DetectionType.footing, dimensioned_width=1.0, dimensioned_length=2.0)
    boq = BillOfQuantities(
        project_id="p",
        lines=[_line("EST-004", ["w1"], raw=10.0), _line("CIM-002", ["f1"], raw=1.0)],
    )
    specs = {"by_family": {
        "dala": {"rebar": "4#3,E#2@20", "stirrups": None, "section_cm": [15, 25]},
        "zapata": {"mesh": "#4@20 A/S"},
    }}  # fmt: skip
    report = compute_steel(boq, [w, z], specs, None, 1.0, 2.7)
    codes = {x.concept_code: x for x in report.lines}
    dala = codes["ACE-002"]
    assert "4#3" in dala.notes[0] and "E#2@20" in dala.notes[0] and "plano" in dala.notes[0]
    longitudinal = 4 * 10.0 * 0.560
    perimeter = 2 * ((0.15 - 0.05) + (0.25 - 0.05)) + 0.075
    stirrups = (math.floor(10.0 / 0.20) + 1) * perimeter * 0.248
    assert dala.quantity == pytest.approx((longitudinal + stirrups) * 1.05, abs=0.01)
    zapata = codes["ACE-003"]
    assert "#4@20" in zapata.notes[0] and "(plano: family)" in zapata.notes[0]


def test_estructura_names_are_reglas_and_elementos():
    # R6: la Tarea 12 guarda exactamente estos dos nombres; si cambian, esto revienta.
    boq, dets = _boq_with_c1()
    est = _estructura_c1()
    assert set(est) == {"reglas", "elementos"}
    with pytest.raises(KeyError):
        compute_steel(
            boq, dets, None, None, 1.0, 2.7, estructura={"rules": est["reglas"], "elementos": []}
        )
    with pytest.raises(KeyError):
        compute_steel(
            boq, dets, None, None, 1.0, 2.7, estructura={"reglas": est["reglas"], "elements": []}
        )


def test_rules_of_each_elements_own_sheet():
    # El gancho de ES-100 es de 6Ø y el de ES-000 de 10Ø; el primer estribo de castillos, 6 cm en
    # ES-100 y 5 cm en ES-000: cada elemento usa los de su hoja.
    gancho = Dato(
        valor={"angulo": 135, "recto_diametros": 10}, fuente="nota", hoja="ES-000",
        texto="135° Y 10Ø", en_conflicto=True,
        alternativas=[Dato(valor={"angulo": 135, "recto_diametros": 6}, fuente="nota",
                           hoja="ES-100", texto="135° Y 6Ø")],
    )  # fmt: skip
    primer = Dato(
        valor=0.05, fuente="nota", hoja="ES-000", texto="PRIMER ESTRIBO A 5 CM", en_conflicto=True,
        alternativas=[
            Dato(valor=0.06, fuente="nota", hoja="ES-100", texto="PRIMER ESTRIBO A 6 CM")
        ],
    )  # fmt: skip
    reglas = R.model_copy(update={"gancho_estribo": gancho,
                                  "primer_estribo_m": {"castillo": primer}})  # fmt: skip
    k_000 = _elemento("K-1", "castillo", (15, 15), 3.0, ["4#3"], "E#2@15", 0.03, hoja="ES-000")
    k_100 = _elemento("K-1", "castillo", (15, 15), 3.0, ["4#3"], "E#2@15", 0.03, hoja="ES-100",
                      det_id="d-K-1-b")  # fmt: skip
    a_000 = acero_elemento(k_000, reglas.para("ES-000"), 0.40)
    a_100 = acero_elemento(k_100, reglas.para("ES-100"), 0.40)
    # ES-000: 2×ROUNDUP(10·0.00635) = 0.14, primero a 0.05: ceil(2.90/0.15) + 1 = 21
    # ES-100: 2×ROUNDUP(6·0.00635) = 0.08, primero a 0.06: ceil(2.88/0.15) + 1 = 21
    assert a_000.kg_por_numero["2"] == pytest.approx(21 * (4 * 0.09 + 0.14) * 0.248)
    assert a_100.kg_por_numero["2"] == pytest.approx(21 * (4 * 0.09 + 0.08) * 0.248)
    assert any("0.05 m" in f for f in a_000.formula) and any("0.06 m" in f for f in a_100.formula)
    # compute_steel resuelve las reglas por la hoja de cada elemento
    dets = [_det(k_000.detection_id, "K-1"), _det(k_100.detection_id, "K-1")]
    boq = BillOfQuantities(project_id="p", lines=[_line("EST-001", [d.detection_id for d in dets])])
    report = compute_steel(boq, dets, None, None, 1.0, 2.7,
                           estructura=_estructura(k_000, k_100, reglas=reglas))  # fmt: skip
    esperado = sum(sum(a.kg_por_numero.values()) for a in (a_000, a_100)) * 1.05
    assert report.lines[0].quantity == pytest.approx(esperado, abs=0.01)


def test_a_bar_without_a_row_falls_back_and_never_raises():
    # Marina: la tabla del plano no trae #2 ni #7 y la estándar tampoco.
    fila, aviso = fila_de_varilla("2", R)
    assert fila is None and "#2" in aviso
    fila, aviso = fila_de_varilla("3", R)
    assert fila == TABLA_ESTANDAR["3"] and "supuesto" in aviso  # la tabla es la estándar
    del_plano = Dato(valor={"3": FilaVarilla(LA1=31).model_dump()}, fuente="cuadro",
                     hoja="ES-000", texto="TABLA DE VARILLAS")  # fmt: skip
    reglas = R.model_copy(update={"tabla_varillas": del_plano})
    fila, aviso = fila_de_varilla("3", reglas)
    assert fila is not None and fila.LA1 == 31 and aviso is None
    fila, aviso = fila_de_varilla("4", reglas)
    assert fila == TABLA_ESTANDAR["4"] and "estándar" in aviso and "supuesto" in aviso
    k = _elemento("K-1", "castillo", (15, 15), 3.0, ["4#3"], "E#2@15", 0.03, det_id="k1")
    a = acero_elemento(k, reglas, 0.40)
    assert a is not None and a.kg_por_numero["2"] > 0
    assert any("#2" in s and "tabla de varillas" in s for s in a.supuestos)
    boq = BillOfQuantities(project_id="p", lines=[_line("EST-001", ["k1"])])
    report = compute_steel(boq, [_det("k1", "K-1")], None, None, 1.0, 2.7,
                           estructura=_estructura(k, reglas=reglas))  # fmt: skip
    assert any("tabla de varillas" in w and "#2" in w for w in report.warnings)


def test_every_unread_beam_is_listed_with_its_reason_never_truncated():
    elementos, dets = [], []
    for i in range(1, 13):
        e = _elemento(f"T-{i}", "trabe", (25, 45), 4.0, [], "E#3@15", 0.04, det_id=f"b{i}")
        e = e.model_copy(update={"avisos": [
            f"longitudinales: el plano lo escribe y no se leyó («{i}#4»); no hay nota de "
            "familia: sin longitudinales"]})  # fmt: skip
        elementos.append(e)
        dets.append(_det(f"b{i}", f"T-{i}", DetectionType.beam_tag, estimated_span_length=4.0))
    boq = BillOfQuantities(project_id="p", lines=[_line("EST-002", [d.detection_id for d in dets])])
    report = compute_steel(boq, dets, None, None, 1.0, 2.7, estructura=_estructura(*elementos))
    assert not any(x.concept_code == "ACE-004" for x in report.lines)
    aviso = next(w for w in report.warnings if "Acero por leer" in w and "trabes" in w)
    for i in range(1, 13):
        assert f"T-{i} (1 pza)" in aviso and f"«{i}#4»" in aviso
    assert "0 de 12" in aviso
    # la etapa de hallazgos lo cuenta como dinero sin costear
    from klave_engine.costing.hallazgos import _RULES

    regla = next(r for r in _RULES if r.group == "acero_sin_cuantificar")
    assert re.search(regla.pattern, aviso)


def test_a_computable_beam_lays_out_from_the_first_stirrup():
    primer = Dato(valor=0.06, fuente="nota", hoja="ES-000", texto="PRIMER ESTRIBO A 6 CM")
    reglas = R.model_copy(update={"primer_estribo_m": {"trabe": primer}})
    t = _elemento("T-7", "trabe", (25, 45), 4.0, ["4#5"], "E#3@15", 0.04, det_id="b1")
    a = acero_elemento(t, reglas, 0.40)
    assert a.kg_por_numero["5"] == pytest.approx(4 * 4.40 * 1.552)
    pieza = 2 * 0.17 + 2 * 0.37 + 0.20
    assert a.kg_por_numero["3"] == pytest.approx(27 * pieza * 0.560)
    dets = [_det("b1", "T-7", DetectionType.beam_tag, estimated_span_length=4.0)]
    boq = BillOfQuantities(project_id="p", lines=[_line("EST-002", ["b1"])])
    report = compute_steel(
        boq, dets, None, None, 1.0, 2.7, estructura=_estructura(t, reglas=reglas)
    )
    trabe = next(x for x in report.lines if x.concept_code == "ACE-004")
    assert trabe.quantity == pytest.approx(sum(a.kg_por_numero.values()) * 1.05, abs=0.01)
    assert any(n.startswith("T-7: 1 pzas × 4#5 E#3@15 sección 25x45 cm") for n in trabe.notes)
    assert not report.warnings


def test_partial_steel_is_said_and_listed():
    # Las varillas se leen y los estribos no: el acero de las varillas cuenta y el de los
    # estribos queda «por leer», con su motivo.
    k = _elemento("K-9", "castillo", (15, 20), 3.0, ["4#3"], None, 0.03, det_id="k9")
    k = k.model_copy(update={"avisos": [
        "estribos: el plano lo escribe y no se leyó («E#2@1S»); no hay nota de familia: sin "
        "estribos"]})  # fmt: skip
    a = acero_elemento(k, R, 0.40)
    assert set(a.kg_por_numero) == {"3"} and a.por_leer
    boq = BillOfQuantities(project_id="p", lines=[_line("EST-001", ["k9"])])
    report = compute_steel(boq, [_det("k9", "K-9")], None, None, 1.0, 2.7,
                           estructura=_estructura(k))  # fmt: skip
    assert report.lines[0].quantity == pytest.approx(4 * 3.40 * 0.560 * 1.05, abs=0.01)
    aviso = next(w for w in report.warnings if "Acero por leer" in w)
    assert "K-9 (1 pza" in aviso and "«E#2@1S»" in aviso and "estribos" in aviso


def test_an_unread_castillo_takes_the_assumed_armado_and_is_listed():
    k = _elemento("K-7", "castillo", (15, 20), 3.0, [], None, 0.03, det_id="k7")
    k = k.model_copy(update={
        "longitudinales": Dato(fuente="detalle", ilegible=True, texto="K-7 · 4#3 + 2#3?"),
        "avisos": ["longitudinales: el plano lo escribe y no se leyó («4#3 + 2#3?»); no hay "
                   "nota de familia: sin longitudinales"],
    })  # fmt: skip
    assert acero_elemento(k, R, 0.40) is None and sin_acero(k)
    boq = BillOfQuantities(project_id="p", lines=[_line("EST-001", ["k7"])])
    report = compute_steel(boq, [_det("k7", "K-7")], None, None, 1.0, 2.7,
                           estructura=_estructura(k))  # fmt: skip
    line = report.lines[0]
    assert line.quantity > 0 and any("Armado supuesto" in n and "K-7" in n for n in line.notes)
    assert any(n.startswith("K-7: 1 pzas × 4#3 E#2@20") and "sin desperdicio" in n for n in line.notes)
    aviso = next(w for w in report.warnings if "Acero por leer" in w)
    assert "K-7" in aviso and "«4#3 + 2#3?»" in aviso and "4#3 E#2@20" in aviso


def test_a_supuesto_section_is_said():
    # R113/R134: la sección propia dibujada y no leída cae a la supuesta; el acero se calcula y
    # la nota dice que la sección es supuesta y por qué.
    t = _elemento("T1-1", "trabe", (25, 45), 4.0, ["3#6"], "2E#3@15", 0.04, det_id="b1",
                  fuente_seccion="supuesto",
                  texto_seccion="sección supuesta de trabe, 25x45 cm: el plano la dibuja y no "
                                "se leyó")  # fmt: skip
    a = acero_elemento(t, R, 0.40)
    assert any("sección" in s and "supuesto" in s and "no se leyó" in s for s in a.por_confirmar)
    boq = BillOfQuantities(project_id="p", lines=[_line("EST-002", ["b1"])])
    report = compute_steel(boq, [_det("b1", "T1-1", DetectionType.beam_tag)], None, None, 1.0,
                           2.7, estructura=_estructura(t))  # fmt: skip
    trabe = next(x for x in report.lines if x.concept_code == "ACE-004")
    assert any("T1-1" in n and "(supuesto)" in n for n in trabe.notes)
    assert any("supuest" in w and "T1-1" in w for w in report.warnings)


def test_an_element_without_length_gets_no_steel_and_is_listed():
    t = _elemento("T-3", "trabe", (25, 45), None, ["4#4"], "E#3@15", 0.04, det_id="b3")
    t = t.model_copy(update={"avisos": ["longitud: sin claro medido ni declarado; sin longitud"]})
    assert acero_elemento(t, R, 0.40) is None
    assert any("longitud" in m for m in sin_acero(t))
    boq = BillOfQuantities(project_id="p", lines=[_line("EST-002", ["b3"])])
    report = compute_steel(boq, [_det("b3", "T-3", DetectionType.beam_tag)], None, None, 1.0,
                           2.7, estructura=_estructura(t))  # fmt: skip
    aviso = next(w for w in report.warnings if "Acero por leer" in w)
    assert "T-3 (1 pza)" in aviso and "sin claro medido" in aviso


def test_kg_by_bar_number_with_the_2_apart():
    # R119: el #2 (alambrón, fy 2530 en Marina) va aparte para que la oficina lo precie aparte.
    fy = {"2": Dato(valor=2530, fuente="nota", hoja="ES-000", texto="F'Y=2530"),
          "3": Dato(valor=4200, fuente="nota", hoja="ES-000", texto="F'Y=4200")}  # fmt: skip
    reglas = R.model_copy(update={"fy_kg_cm2": fy})
    k = _elemento("K-1", "castillo", (15, 15), 3.0, ["4#3"], "E#2@15", 0.03, det_id="k1")
    boq = BillOfQuantities(project_id="p", lines=[_line("EST-001", ["k1"])])
    report = compute_steel(boq, [_det("k1", "K-1")], None, None, 1.0, 2.7,
                           estructura=_estructura(k, reglas=reglas))  # fmt: skip
    nota = next(n for n in report.lines[0].notes if n.startswith("Kg por número"))
    a = acero_elemento(k, reglas, 0.40)
    assert f"#3 {a.kg_por_numero['3'] * 1.05:,.2f} kg" in nota
    assert "#2 aparte" in nota and "alambrón" in nota and "fy 2530" in nota
    assert f"{a.kg_por_numero['2'] * 1.05:,.2f} kg" in nota


def test_zone_length_stated_on_the_definition_wins():
    z = [Zona(tramo="extremos", separacion_m=.10, longitud_m=0.30),
         Zona(tramo="centro", separacion_m=.20)]  # fmt: skip
    # 0.05, 0.15, 0.25 en cada extremo; entre 0.25 y 2.85: ceil(2.60/0.20) − 1 = 12
    assert posiciones(3.10, z, None, 0.60) == 3 + 3 + 12


def test_zones_that_overlap_are_one_spacing():
    z = [Zona(tramo="extremos", separacion_m=0.10), Zona(tramo="centro", separacion_m=0.20)]
    # 1.00 m con extremos de 0.60: todo a @10, del primero a s/2 al último
    assert posiciones(1.00, z, None, 0.60) == math.ceil(0.90 / 0.10 - 1e-9) + 1


def test_unsupported_zones_raise_and_the_set_goes_unread():
    with pytest.raises(ValueError):
        posiciones(3.0, [Zona(tramo="extremos", separacion_m=0.10)], None, 0.6)
    with pytest.raises(ValueError):
        posiciones(3.0, [Zona(tramo="todo", separacion_m=None)], None, 0.0)
    k = _elemento("K-2", "castillo", (15, 15), 3.0, ["4#3"], "E#3@15", 0.03)
    sin_separacion = [j.model_copy(update={"zonas": []}) for j in k.estribos.valor]
    k = k.model_copy(update={"estribos": k.estribos.model_copy(update={"valor": sin_separacion})})
    a = acero_elemento(k, R, 0.40)
    assert set(a.kg_por_numero) == {"3"} and any("separación" in p for p in a.por_leer)


def test_kg_table_is_the_steel_table():
    for numero in ("2", "3", "8"):
        assert numero in BAR_KG_PER_M


@pytest.mark.parametrize(
    "orden",
    ["import klave_engine.costing.steel, klave_engine.estructura.acero",
     "import klave_engine.estructura.acero, klave_engine.costing.steel"],
)  # fmt: skip
def test_no_import_cycle(orden):
    # R17: costing.steel lee el armado de estructura y estructura.acero pesa con costing.steel.
    r = subprocess.run([sys.executable, "-c", orden], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_the_cost_report_passes_the_model_to_the_steel_stage(monkeypatch):
    from klave_engine.costing import report as report_module
    from klave_engine.costing.models import CostingConfig
    from klave_engine.dxf.units import DrawingUnits

    vistos: list[dict | None] = []
    original = report_module.compute_steel

    def espia(*args, **kwargs):
        vistos.append(kwargs.get("estructura"))
        return original(*args, **kwargs)

    monkeypatch.setattr(report_module, "compute_steel", espia)
    units = DrawingUnits(unit="m", source="declared", confidence=1.0)
    est = _estructura_c1()
    report_module.generate_cost_report(
        "p", [_det("c1", "C-1")], units, CostingConfig(), None, None, estructura=est
    )
    report_module.generate_cost_report("p", [_det("c1", "C-1")], units, CostingConfig())
    assert vistos == [est, None]


def test_the_cover_is_the_elements_own():
    # El recubrimiento del elemento (el de su familia en su hoja) manda, no el estándar.
    k3 = _elemento("K-1", "castillo", (20, 20), 3.0, ["4#3"], "E#2@15", 0.03)
    k4 = _elemento("K-1", "castillo", (20, 20), 3.0, ["4#3"], "E#2@15", 0.04)
    a3, a4 = acero_elemento(k3, R, 0.40), acero_elemento(k4, R, 0.40)
    n = math.ceil((3.0 - 0.15) / 0.15 - 1e-9) + 1
    assert a3.kg_por_numero["2"] == pytest.approx(n * (4 * 0.14 + 0.14) * 0.248)
    assert a4.kg_por_numero["2"] == pytest.approx(n * (4 * 0.12 + 0.14) * 0.248)


def test_without_the_model_every_assumed_castillo_is_named():
    # R148a: sin el modelo, cada castillo con el armado supuesto se nombra (antes, 8 y ya).
    dets = [_det(f"k{i}", f"K-{i}") for i in range(1, 11)]
    boq = BillOfQuantities(project_id="p", lines=[_line("EST-001", [d.detection_id for d in dets])])
    report = compute_steel(boq, dets, None, None, 1.0, 2.7)
    aviso = next(w for w in report.warnings if "Acero por leer" in w)
    nota = next(n for n in report.lines[0].notes if n.startswith("Armado supuesto"))
    for i in range(1, 11):
        assert f"K-{i} (sin armado y sección)" in aviso and f"K-{i}" in nota.split(": ")[1].split(
            ", "
        )
    assert "4#3 E#2@20" in aviso
    # una marca con su armado y sin su sección dice sólo lo que le falta
    specs = {"by_mark": {"K-1": {"rebar": "6#8+6#6", "stirrups": None, "section_cm": None}}}
    report = compute_steel(boq, dets, specs, None, 1.0, 2.7)
    aviso = next(w for w in report.warnings if "Acero por leer" in w)
    assert "K-1 (sin sección)" in aviso and "K-2 (sin armado y sección)" in aviso


def test_an_unread_beam_says_every_unread_field():
    t = _elemento("CTA-1", "contratrabe", (35, 80), 2.3, [], None, 0.05, det_id="b1")
    t = t.model_copy(
        update={
            "avisos": [
                "longitudinales: el plano lo escribe y no se leyó («3#8», «2#8+2#6»); no hay nota "
                "de familia: sin longitudinales",
                "estribos: el plano lo escribe y no se leyó («E#4», «1@6,8@10», «@15»); no hay "
                "nota de familia: sin estribos",
            ]
        }
    )
    boq = BillOfQuantities(project_id="p", lines=[_line("CIM-008", ["b1"])])
    report = compute_steel(
        boq, [_det("b1", "CTA-1", DetectionType.beam_tag)], None, None, 1.0, 2.7,
        estructura=_estructura(t),
    )  # fmt: skip
    aviso = next(w for w in report.warnings if "Acero por leer" in w)
    assert "«3#8», «2#8+2#6»" in aviso and "«E#4», «1@6,8@10», «@15»" in aviso


def test_model_elements_outside_the_budget_lines_are_said():
    # Un castillo que el presupuesto no cuenta (la planta de cimentación) y una trabe sin claro
    # (no entra a EST-002): su acero no se suma, y se dice con lo que pesaría o por qué no.
    k = _elemento("K-4", "castillo", (15, 30), 2.9, ["6#4"], "EYG#3@15", 0.03, det_id="k0",
                  hoja="ES-000")  # fmt: skip
    t = _elemento("T4-1", "trabe", (25, 40), None, ["3#4"], "E#3@15", 0.04, det_id="t0")
    t = t.model_copy(update={"avisos": ["longitud: ninguna línea corre junto a ella; sin claro"]})
    dentro = _elemento("K-1", "castillo", (15, 15), 3.0, ["4#3"], "E#2@15", 0.03, det_id="k1")
    boq = BillOfQuantities(project_id="p", lines=[_line("EST-001", ["k1"])])
    report = compute_steel(boq, [_det("k1", "K-1")], None, None, 1.0, 2.7,
                           estructura=_estructura(k, t, dentro))  # fmt: skip
    aviso = next(w for w in report.warnings if "fuera del presupuesto" in w)
    kg = acero_elemento(k, R, 0.40).total_kg() * 1.05
    assert f"K-4 (1 pza) en ES-000: {kg:,.1f} kg" in aviso
    assert "T4-1 (1 pza)" in aviso and "sin claro" in aviso
    assert "K-1" not in aviso


# ------------------------------------------------------------------ ronda de arreglos 1


def _con_cover(e, dato):
    return e.model_copy(update={"recubrimiento_m": dato})


def test_a_cover_taken_from_a_range_is_said():
    # R212: «3.0 A 5.0 CM LIBRES EN CASTILLOS» da 3 cm, el mínimo: es un supuesto y se dice.
    rango = Dato(valor=0.03, fuente="nota", hoja="ES-000", texto="3.0 A 5.0 CM LIBRES EN CASTILLOS")
    k = _con_cover(_elemento("K-1", "castillo", (15, 15), 3.0, ["4#3"], "E#2@15", 0.03), rango)
    a = acero_elemento(k, R, 0.40)
    assert any("recubrimiento 3.0 cm, el mínimo de «3.0 A 5.0 CM»" in s for s in a.supuestos)
    dibujado = Dato(valor=0.05, fuente="seccion_dibujada", hoja="ES-000", texto="K-12 · 5 cm",
                    alternativas=[rango])  # fmt: skip
    k12 = _elemento("K-12", "castillo", (30, 30), 3.0, ["4#6"], "E#3@15", 0.03)
    k12 = _con_cover(k12, dibujado)
    assert not any("mínimo" in s for s in acero_elemento(k12, R, 0.40).supuestos)


def test_assumed_shapes_on_an_elongated_section_are_to_confirm():
    # R212: K-7 20×55 con 2E: la práctica supone perimetral + rombo y el corte dibuja un amarre
    # interior; en una sección con h/b ≥ 2 la forma supuesta queda por confirmar, con la marca.
    k7 = _elemento("K-7", "castillo", (20, 55), 3.2, ["4#5+4#4"], "2E#3@20", 0.03, det_id="k7")
    a = acero_elemento(k7, R, 0.40)
    assert any("alargada" in d and "por confirmar" in d for d in a.por_confirmar)
    k12 = _elemento("K-12", "castillo", (30, 30), 3.2, ["4#6+4#4"], "2E#3@15", 0.05)
    assert not any("alargada" in d for d in acero_elemento(k12, R, 0.40).por_confirmar)
    k5 = _elemento("K-5", "castillo", (20, 30), 3.2, ["6#4"], "EYG#3@15", 0.03)  # 1 + grapa
    assert not any("alargada" in d for d in acero_elemento(k5, R, 0.40).por_confirmar)
    boq = BillOfQuantities(project_id="p", lines=[_line("EST-001", ["k7"])])
    report = compute_steel(boq, [_det("k7", "K-7")], None, None, 1.0, 2.7,
                           estructura=_estructura(k7))  # fmt: skip
    aviso = next(w for w in report.warnings if "por confirmar" in w)
    assert "K-7 (1 pza)" in aviso and "alargada" in aviso


def test_a_partial_weight_says_so_wherever_it_appears():
    # R213 (K-15A): las varillas pesan y los estribos no; la nota de la marca y la entrada fuera
    # del presupuesto lo dicen junto al número. R215: las notas por marca, sin desperdicio.
    area = Dato(valor={"area_cm2": 2300.0}, fuente="medido", hoja="ES-100", texto="contorno")
    k = _elemento("K-15A", "castillo", (30, 60), 3.6, ["6#8+6#6"], "4E#3EXT@10 CENTRO@20", 0.03,
                  det_id="k1", hoja="ES-100")  # fmt: skip
    k = k.model_copy(update={"seccion_cm": area})
    otra_area = area.model_copy(update={"valor": {"area_cm2": 2300.1}})
    k2 = k.model_copy(update={"detection_id": "k2", "hoja": "ES-200", "seccion_cm": otra_area})
    fuera = k.model_copy(update={"detection_id": "k0", "hoja": "ES-000"})
    boq = BillOfQuantities(project_id="p", lines=[_line("EST-001", ["k1", "k2"])])
    report = compute_steel(boq, [_det("k1", "K-15A"), _det("k2", "K-15A")], None, None, 1.0, 2.7,
                           estructura=_estructura(k, k2, fuera))  # fmt: skip
    notas = [n for n in report.lines[0].notes if n.startswith("K-15A:")]
    assert len(notas) == 1 and notas[0].startswith("K-15A: 2 pzas")  # 2300.0 y 2300.1: una
    assert "(sólo varillas longitudinales; estribos por leer)" in notas[0]
    assert "kg sin desperdicio" in notas[0]
    entrada = next(w for w in report.warnings if "fuera del presupuesto" in w)
    assert "K-15A (1 pza) en ES-000:" in entrada
    assert "(sólo varillas longitudinales; estribos por leer)" in entrada
    por_leer = next(w for w in report.warnings if w.startswith("Acero por leer"))
    assert por_leer.count("K-15A (") == 1


def test_a_castillo_without_declared_stirrups_is_not_unread():
    # R215: K-X («CASTILLO AHOGADO / REFUERZO 1#4») no declara estribos: no es «por leer».
    kx = _elemento("K-X", "castillo", (20, 40), 3.2, ["1#4"], None, 0.03, det_id="kx")
    a = acero_elemento(kx, R, 0.40)
    assert not a.por_leer and a.sin_estribos_declarados
    boq = BillOfQuantities(project_id="p", lines=[_line("EST-001", ["kx"])])
    report = compute_steel(boq, [_det("kx", "K-X")], None, None, 1.0, 2.7,
                           estructura=_estructura(kx))  # fmt: skip
    assert not any(w.startswith("Acero por leer") for w in report.warnings)
    nota = next(n for n in report.lines[0].notes if n.startswith("K-X:"))
    assert "(sin estribos declarados)" in nota


def test_the_path_without_the_model_never_calls_a_default_the_drawings():
    # R214: sin el modelo (cada corrida del pipeline hasta la Tarea 12), K-15A trae su armado y
    # no su sección: la sección es supuesta y se dice; sus 4E por zonas no se pesan sobre una
    # sección supuesta; el método sin modelo se dice una vez.
    dets = [_det("k1", "K-15A")]
    boq = BillOfQuantities(project_id="p", lines=[_line("EST-001", ["k1"])])
    specs = {"by_mark": {"K-15A": {"rebar": "6#8+6#6", "stirrups": "4E#3 EXT@10 CENTRO@20",
                                   "section_cm": None}}}  # fmt: skip
    report = compute_steel(boq, dets, specs, None, 1.0, 3.0)
    line = report.lines[0]
    nota = next(n for n in line.notes if n.startswith("K-15A:"))
    assert "(supuesta)" in nota and "(plano)" not in nota
    assert line.quantity == pytest.approx((6 * 3.973 + 6 * 2.235) * 3.40 * 1.05, abs=0.01)
    assert any("4E#3 EXT@10 CENTRO@20" in n and "no se pesan" in n for n in line.notes)
    assert not any(n.startswith("Armado supuesto") and "K-15A" in n for n in line.notes)
    assert any(n.startswith("Sección supuesta") and "K-15A" in n for n in line.notes)
    aviso = next(w for w in report.warnings if w.startswith("Acero por leer"))
    assert "K-15A (sin sección" in aviso and "no se pesan" in aviso
    metodo = "método sin modelo estructural: recubrimiento 2.5 cm, gancho 7.5 cm, cada pieza"
    assert sum(metodo in n for n in line.notes) == 1
    # una sola pieza uniforme sobre la sección supuesta sí se pesa, como siempre
    specs["by_mark"]["K-15A"]["stirrups"] = "E#3@15"
    uno = compute_steel(boq, dets, specs, None, 1.0, 3.0)
    assert uno.lines[0].quantity > line.quantity
