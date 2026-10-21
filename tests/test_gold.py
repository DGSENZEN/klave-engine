"""Gold set: capture folds reviews into labels; the runner guards regressions."""

from klave_engine.common.config import get_settings
from klave_engine.costing.reviews import DetectionReview, load_reviews, save_reviews
from klave_engine.evals.fixtures import write_demo_project
from klave_engine.evals.gold import capture, evaluate_entry, load_entries, save_entry
from klave_engine.pipeline import run_full_pipeline


def test_capture_and_evaluate_round_trip(data_dir, tmp_path):
    settings = get_settings()
    root = tmp_path / "demo"
    write_demo_project(root)
    result = run_full_pipeline(root, settings)
    assert result.detections

    baseline = capture(root, "demo", settings)
    assert baseline.status == "baseline"
    assert baseline.files and all(len(v) == 64 for v in baseline.files.values())
    assert baseline.labels["column_tag"] and baseline.baseline_f1["column_tag"] == 1.0

    # A human excludes one detection and confirms another: the entry becomes
    # partial, the excluded label leaves the expectations, and the engine —
    # which still produces it — now scores below 1 on that type.
    control_dir = root / settings.processed_dir_name
    reviews = load_reviews(control_dir)
    column = next(d for d in result.detections if d.detection_type.value == "column_tag")
    wall = next(d for d in result.detections if d.detection_type.value == "wall")
    reviews.detections[column.display_label or column.label] = DetectionReview(status="excluded")
    reviews.detections[wall.display_label or wall.label] = DetectionReview(status="confirmed")
    save_reviews(control_dir, reviews)

    partial = capture(root, "demo", settings)
    assert partial.status == "partial"
    assert partial.excluded == [column.display_label or column.label]
    assert partial.confirmed == [wall.display_label or wall.label]
    assert len(partial.labels["column_tag"]) == len(baseline.labels["column_tag"]) - 1
    assert partial.baseline_f1["column_tag"] < 1.0

    gold_dir = tmp_path / "gold"
    save_entry(partial, gold_dir)
    assert [e.drawing_id for e in load_entries(gold_dir)] == ["demo"]

    outcome = evaluate_entry(partial, settings)
    assert outcome.available and outcome.fingerprint_matches
    assert outcome.passed  # unchanged engine never scores below its own baseline
    assert outcome.excluded_present == partial.excluded  # the debt is visible
    assert outcome.confirmed_missing == []


def test_missing_source_is_reported_not_failed(data_dir, tmp_path):
    from datetime import UTC, datetime

    from klave_engine.evals.gold import GoldEntry

    entry = GoldEntry(
        drawing_id="ausente", source=str(tmp_path / "nada"), files={},
        status="baseline", captured_at=datetime.now(UTC),
    )
    outcome = evaluate_entry(entry, get_settings())
    assert not outcome.available and outcome.passed and "no disponible" in outcome.message


# ------------------------------------------------------------- la cerca estructural

import json  # noqa: E402
from datetime import UTC, datetime  # noqa: E402

import pytest  # noqa: E402
from klave_engine.evals import gold as g  # noqa: E402
from klave_engine.evals.gold import EstructuraExpectation, score_estructura  # noqa: E402
from pydantic import ValidationError  # noqa: E402


def _est(
    familias: dict[str, dict[str, dict[str, int]]] | None = None,
    hallazgos: dict[str, list[list[str]]] | None = None,
) -> dict:
    """Un ``estructura.json`` mínimo: por familia, sus colocaciones por hoja (y sus demás
    cuentas); por clave ``"numero/severidad"``, las marcas de cada hallazgo."""
    resumen, elementos, verificaciones = [], [], []
    for familia, d in (familias or {}).items():
        hojas = d.get("hojas", {})
        t = {"familia": familia, "colocaciones": sum(hojas.values()), "con_definicion": 0,
             "criticos_total": 0, "criticos_del_plano": 0}  # fmt: skip
        t.update(d.get("campos", {}))
        resumen.append(t)
        for hoja, n in hojas.items():
            elementos += [{"familia": familia, "hoja": hoja}] * n
    for clave, lista in (hallazgos or {}).items():
        numero, _, severidad = clave.partition("/")
        verificaciones += [
            {"numero": int(numero), "severidad": severidad, "marcas": m} for m in lista
        ]
    return {"resumen": resumen, "elementos": elementos, "verificaciones": verificaciones}


_CAMPOS = {"con_definicion": 2, "criticos_total": 8, "criticos_del_plano": 6}
_BASE = {"castillo": {"hojas": {"ES-100": 1, "ES-200": 1}, "campos": _CAMPOS}}
_HALL = {"1/bloquea": [["T4-3"]], "2/aviso": [["K-0"], ["P-2"]]}


def test_estructura_fence_is_exact(tmp_path):
    want = EstructuraExpectation(
        por_familia={"castillo": {"colocaciones": 2, "con_definicion": 2,
                                  "criticos_total": 8, "criticos_del_plano": 6}},
        por_hoja={"castillo": {"ES-100": 1, "ES-200": 1}},
        verificaciones={"8/duda": 1}, hallazgos={"8/duda": ["K-5"]},
    )
    base = _est(_BASE, {"8/duda": [["K-5"]]})
    ok, diffs = score_estructura(want, base)
    assert ok and diffs == []
    menos = _est({"castillo": {**_BASE["castillo"], "campos": {**_BASE["castillo"]["campos"],
                                                               "con_definicion": 1}}},
                 {"8/duda": [["K-5"]]})  # fmt: skip
    ok2, diffs2 = score_estructura(want, menos)
    assert not ok2 and "castillo" in diffs2[0]


def test_estructura_fence_identities_not_only_counts():
    want = g.estructura_from_json(_est(_BASE, _HALL))
    assert want.hallazgos == {"1/bloquea": ["T4-3"], "2/aviso": ["K-0", "P-2"]}
    assert want.por_hoja == {"castillo": {"ES-100": 1, "ES-200": 1}}
    # Un hallazgo cambiado por otro, con la misma cuenta: falla y dice cuál.
    ok, diffs = score_estructura(want, _est(_BASE, {**_HALL, "1/bloquea": [["T4-4"]]}))
    assert not ok
    assert diffs == ["verificación 1/bloquea, hallazgos: faltan ['T4-3'], sobran ['T4-4']"]
    # Una colocación que se cambia de hoja, con el mismo total: falla.
    mudada = _est({"castillo": {**_BASE["castillo"], "hojas": {"ES-100": 2}}},
                  {"1/bloquea": [["T4-3"]], "2/aviso": [["K-0"], ["P-2"]]})
    ok, diffs = score_estructura(want, mudada)
    assert not ok and sorted(diffs) == ["castillo en ES-100: esperado 1, motor 2",
                                        "castillo en ES-200: esperado 1, motor 0"]
    # Por su total también: «2» cerca a los dos hallazgos, sean de la severidad que sean.
    total = EstructuraExpectation(por_familia=want.por_familia, por_hoja=want.por_hoja,
                                  verificaciones={"1/bloquea": 1, "2": 2},
                                  hallazgos={"1/bloquea": ["T4-3"], "2": ["K-0", "P-2"]})
    otro = _est(_BASE, {"1/bloquea": [["T4-3"]], "2/aviso": [["K-0"]], "2/duda": [["D-1C"]]})
    ok, diffs = score_estructura(total, otro)
    assert not ok and diffs == ["verificación 2, hallazgos: faltan ['P-2'], sobran ['D-1C']"]
    # Un hallazgo sin marcas tiene su identidad; varias marcas, unidas y ordenadas.
    assert g.identidad_de_hallazgo({"marcas": []}) == g.SIN_MARCA
    assert g.identidad_de_hallazgo({"marcas": ["K-2", "C-1", "K-2"]}) == "C-1+K-2"


def test_estructura_fence_everything_not_fenced_must_be_zero_or_excused():
    hall = {"1/bloquea": [["T4-3"]], "2/duda": [["K-0"]]}
    want = EstructuraExpectation(
        por_familia={"castillo": {"colocaciones": 2, "con_definicion": 2}},
        por_hoja={"castillo": {"ES-100": 1, "ES-200": 1}},
        verificaciones={"1/bloquea": 1, "2": 1}, hallazgos={"1/bloquea": ["T4-3"], "2": ["K-0"]},
        sin_cerca={"por_familia.castillo.criticos_total": "no medido",
                   "verificaciones.7": "pendiente de la transcripción"},
    )
    campos = {"con_definicion": 2, "criticos_del_plano": 0, "criticos_total": 8}
    fam = {"castillo": {"hojas": {"ES-100": 1, "ES-200": 1}, "campos": campos}}
    assert score_estructura(want, _est(fam, hall)) == (True, [])
    # Una familia nueva con colocaciones que el gold no conoce: falla.
    ok, diffs = score_estructura(want, _est({**fam, "trabe": {"hojas": {"ES-100": 3}}}, hall))
    assert not ok and any("trabe" in d for d in diffs)
    # Un campo no cercado ni excusado de una familia cercada: debe ser 0.
    cp = {"castillo": {**fam["castillo"], "campos": {**campos, "criticos_del_plano": 1}}}
    ok, diffs = score_estructura(want, _est(cp, hall))
    assert not ok and any("castillo.criticos_del_plano" in d for d in diffs)
    # Lo excusado no se mide: criticos_total y la verificación 7 pueden moverse.
    libre = {"castillo": {**fam["castillo"], "campos": {**campos, "criticos_total": 999}}}
    assert score_estructura(want, _est(libre, {**hall, "7/bloquea": [["X"]] * 40})) == (True, [])
    # Una severidad no cercada de una verificación cercada por severidad: debe ser 0.
    ok, diffs = score_estructura(want, _est(fam, {**hall, "1/aviso": [[], []]}))
    assert not ok and any("1/aviso" in d for d in diffs)
    # Una verificación cercada por su total cuenta todas sus severidades.
    ok, diffs = score_estructura(want, _est(fam, {**hall, "2/aviso": [["P-2"]]}))
    assert not ok and any(d.startswith("verificación 2:") for d in diffs)
    # Una verificación que no aparece en el gold: debe ser 0.
    ok, diffs = score_estructura(want, _est(fam, {**hall, "11/duda": [[]]}))
    assert not ok and any("11" in d for d in diffs)
    # Y una cercada que desaparece también falla (exacta, no «a lo más»).
    ok, diffs = score_estructura(want, _est(fam, {"1/bloquea": [["T4-3"]]}))
    assert not ok and any(d.startswith("verificación 2:") for d in diffs)
    # Lo mismo por severidad: un 1/bloquea cercado que desaparece falla.
    ok, diffs = score_estructura(want, _est(fam, {"2/duda": [["K-0"]]}))
    assert not ok and diffs == ["verificación 1/bloquea: esperado 1, motor 0"]


def test_estructura_fence_without_estructura_json_fails():
    want = EstructuraExpectation(por_familia={"castillo": {"con_definicion": 1}})
    ok, diffs = score_estructura(want, None)
    assert not ok and "estructura.json" in diffs[0]


@pytest.mark.parametrize("datos", [
    {"por_familia": {"castillo": {"colocacion": 1}}},
    {"verificaciones": {"1/grave": 1}, "hallazgos": {"1/grave": ["X"]}},
    {"sin_cerca": {"castillo": "sin prefijo"}},
    {"sin_cerca": {"verificaciones.7": " "}},
    # La clave con tilde de la Tarea 16 no se tira callada.
    {"transcripción": "evals/transcripcion/x.json"},
    # Cercado y excusado a la vez.
    {"por_familia": {"zapata": {"con_definicion": 0}}, "sin_cerca": {"por_familia.zapata": "r"}},
    {"por_familia": {"zapata": {"con_definicion": 0}},
     "sin_cerca": {"por_familia.zapata.con_definicion": "r"}},
    {"verificaciones": {"1/bloquea": 1}, "hallazgos": {"1/bloquea": ["T4-3"]},
     "sin_cerca": {"verificaciones.1": "r"}},
    {"verificaciones": {"7": 0}, "sin_cerca": {"verificaciones.7/duda": "r"}},
    # Un número por su total y por severidad.
    {"verificaciones": {"7": 0, "7/duda": 0}},
    # Fuera de 1–11.
    {"verificaciones": {"12/duda": 0}},
    {"verificaciones": {"0": 0}},
    {"sin_cerca": {"verificaciones.12": "r"}},
    # Cuentas sin sus hallazgos o sin sus hojas, o que no cuadran.
    {"verificaciones": {"2/aviso": 1}},
    {"verificaciones": {"2/aviso": 1}, "hallazgos": {"2/aviso": ["K-0", "P-2"]}},
    {"verificaciones": {"2/aviso": 2}, "hallazgos": {"2/aviso": ["P-2", "K-0"]}},
    {"hallazgos": {"2/aviso": []}},
    {"por_familia": {"castillo": {"colocaciones": 2}}},
    {"por_familia": {"castillo": {"colocaciones": 2}}, "por_hoja": {"castillo": {"ES-100": 1}}},
    {"por_hoja": {"castillo": {"ES-100": 1}}},
])
def test_estructura_fence_rejects_what_cannot_be_meant(datos):
    with pytest.raises(ValidationError):
        EstructuraExpectation.model_validate(datos)


def test_gold_entry_and_money_reject_unknown_keys():
    with pytest.raises(ValidationError):
        g.MoneyExpectation.model_validate({"concepts": {}, "sin_cercas": {}})
    with pytest.raises(ValidationError):
        g.GoldEntry.model_validate({"drawing_id": "x", "source": "s", "files": {},
                                    "status": "baseline", "captured_at": "2026-10-18T00:00:00Z",
                                    "estructuras": {}})  # fmt: skip
    # Las entradas que ya están en el gold se leen sin un campo de más.
    assert len(g.load_entries()) >= 9


def test_fresh_capture_never_copies_the_engine_fence_and_evaluation_uses_it(data_dir, tmp_path):
    from klave_engine.evals.gold import render_markdown

    settings = get_settings()
    root = tmp_path / "demo"
    write_demo_project(root)
    entry = capture(root, "demo", settings, fresh=True)
    assert entry.estructura is None  # la cerca estructural nunca sale de copiar al motor
    gold_dir = tmp_path / "gold"
    entry.estructura = EstructuraExpectation(sin_cerca={"verificaciones.7/bloquea": "unidades"})
    save_entry(entry, gold_dir)
    with pytest.raises(g.CambioDeCerca):  # la semilla dice «cero»: el motor da más
        g.capture_estructura(gold_dir, "demo", settings)
    g.capture_estructura(gold_dir, "demo", settings, acepto=True)
    entry = load_entries(gold_dir)[0]
    assert entry.estructura is not None
    # Lo que el demo dibuja (a mano: 3 etiquetas de columna, 1 de trabe, 2 zapatas sin marca).
    assert entry.estructura.por_familia["columna"]["colocaciones"] == 3
    assert entry.estructura.hallazgos["1/bloquea"] == ["B-1", "C-1", "C-2"]
    assert "7/bloquea" not in entry.estructura.verificaciones
    assert entry.estructura.sin_cerca == {"verificaciones.7/bloquea": "unidades"}
    # Sin cambios, recapturar no pide --acepto.
    g.capture_estructura(gold_dir, "demo", settings)
    ok = evaluate_entry(entry, settings)
    assert ok.passed and ok.estructura_passed is True and ok.estructura_diffs == []

    movida = entry.model_copy(deep=True)
    assert movida.estructura is not None
    movida.estructura.por_familia["columna"]["colocaciones"] = 4
    movida.estructura.por_hoja["columna"] = {"drawings/S-101.dxf": 4}
    movida.estructura.verificaciones["7/duda"] = 0
    del movida.estructura.hallazgos["7/duda"]
    bad = evaluate_entry(movida, settings)
    assert not bad.passed and bad.estructura_passed is False
    assert any(d.startswith("columna.colocaciones") for d in bad.estructura_diffs)
    assert any(d.startswith("verificación 7/duda") for d in bad.estructura_diffs)
    md = render_markdown({"evaluated_at": "x", "all_passed": False, "entries": [bad.model_dump()]})
    assert "### Lectura estructural" in md and "columna.colocaciones" in md
    sin = entry.model_copy(deep=True)
    sin.estructura = None
    out = evaluate_entry(sin, settings)
    assert out.passed and out.estructura_passed is None


def test_evaluation_checks_the_transcription_against_the_runs_schedules(data_dir, tmp_path):
    settings = get_settings()
    root = tmp_path / "demo"
    write_demo_project(root)
    entry = capture(root, "demo", settings, fresh=True)
    vacia = tmp_path / "t.json"
    vacia.write_text(json.dumps({"lecturas": []}))
    entry.estructura = EstructuraExpectation(
        transcripcion=str(vacia), sin_cerca={"por_familia.columna": "r", "por_familia.trabe": "r",
                                             "por_familia.zapata": "r", "verificaciones.1": "r",
                                             "verificaciones.7": "r"})  # fmt: skip
    ok = evaluate_entry(entry, settings)  # el demo no define nada: nada que leer
    assert ok.passed and ok.transcripcion_passed is True
    lectura = {"marca": "C-1", "hoja": "S-101", "longitudinal": "4#4"}
    vacia.write_text(json.dumps({"lecturas": [lectura]}))
    bad = evaluate_entry(entry, settings)
    assert not bad.passed and bad.transcripcion_passed is False
    assert bad.transcripcion_diffs == ["C-1 en S-101: la transcripción la lee y el motor no"]


def test_estructura_from_json_drops_what_is_excused():
    from klave_engine.evals.gold import estructura_from_json

    est = _est({"castillo": {"hojas": {"ES-100": 2}, "campos": {"con_definicion": 2,
                                                              "criticos_total": 8,
                                                              "criticos_del_plano": 5}},
                "zapata": {"hojas": {"ES-000": 3}, "campos": {"criticos_total": 9}},
                "general": {}},
               {"7/duda": [["K-1"]], "1/aviso": [[]], "1/bloquea": [["T4-3"]]})  # fmt: skip
    razones = {"por_familia.zapata": "r", "por_familia.castillo.criticos_del_plano": "r",
               "verificaciones.7": "r", "verificaciones.1/aviso": "r"}
    want = estructura_from_json(est, razones)
    assert want.por_familia == {"castillo": {"colocaciones": 2, "con_definicion": 2,
                                             "criticos_total": 8}}
    assert want.por_hoja == {"castillo": {"ES-100": 2}}
    assert want.verificaciones == {"1/bloquea": 1} and want.hallazgos == {"1/bloquea": ["T4-3"]}
    assert want.sin_cerca == razones
    assert score_estructura(want, est) == (True, [])
    full = estructura_from_json(est)
    assert full.verificaciones == {"1/bloquea": 1, "1/aviso": 1, "7/duda": 1}
    assert full.hallazgos["1/aviso"] == [g.SIN_MARCA]
    assert "general" not in full.por_familia and score_estructura(full, est) == (True, [])


def _report(lines, direct=10.0):
    from klave_engine.costing.models import BoqLine, CostReport

    boq = [BoqLine.model_construct(concept_code=c, quantity=q, unit="PZA", variants=[],
                                   unpriced=True) for c, q in lines]  # fmt: skip
    report = CostReport.model_construct()
    report.boq = type("B", (), {"lines": boq, "direct_cost_total": direct})()
    return report


def test_money_fence_excuses_listed_concepts_and_the_direct_cost():
    from klave_engine.evals.gold import MoneyExpectation, money_from_report, score_money

    report = _report([("CIM-010", 23.0), ("EST-001", 44.379)])
    fence = money_from_report(report, {"EST-001": "storey", "costo_directo": "no verificado"})
    assert set(fence.concepts) == {"CIM-010"} and fence.direct_cost is None
    scores, cost_passed, unexpected = score_money(fence, report)
    assert all(s.passed for s in scores) and cost_passed is None and unexpected == []
    # Sin la excusa, el renglón no cercado es un concepto nuevo y falla.
    bare = MoneyExpectation(concepts=fence.concepts)
    assert score_money(bare, report)[2] == ["EST-001"]


def _entrada(tmp_path, **kw):
    (tmp_path / "src" / "drawings").mkdir(parents=True, exist_ok=True)
    return g.GoldEntry(drawing_id="x", source=str(tmp_path / "src"), files={}, status="baseline",
                       captured_at=datetime(2026, 10, 18, tzinfo=UTC), **kw)  # fmt: skip


def test_capture_money_keeps_verified_rows_and_refuses_fenced_changes(tmp_path, monkeypatch):
    gold_dir = tmp_path / "gold"
    entry = _entrada(tmp_path, money=g.MoneyExpectation(
        concepts={"CIM-010": g.QuantityExpectation(quantity=23, unit="PZA", tolerance_pct=0.0,
                                                   source="crudo", note="contado en crudo"),
                  "CIM-001": g.QuantityExpectation(quantity=10.0, unit="M3", note="deriva")},
        direct_cost=10.0, sin_cerca={"EST-001": "storey"},
    ))
    g.save_entry(entry, gold_dir)
    # Una corrida que mueve CIM-010 (verificado) y no CIM-001: lo verificado no se toca.
    report = _report([("CIM-010", 25.0), ("CIM-001", 10.0), ("EST-001", 44.379)])
    report.boq.lines[1].unit = "M3"
    monkeypatch.setattr(g, "_fresh_run", lambda *_a, **_k: ([], report, None))
    g.capture_money(gold_dir, only="x")
    again = g.load_entries(gold_dir)[0].money
    assert again is not None
    assert again.concepts["CIM-010"].quantity == 23 and again.concepts["CIM-010"].source == "crudo"
    assert again.concepts["CIM-001"].note == "deriva" and "EST-001" not in again.concepts
    assert again.sin_cerca == {"EST-001": "storey"}
    # Una corrida que mueve un renglón del motor cercado: se niega sin --acepto y no escribe.
    report2 = _report([("CIM-010", 25.0), ("CIM-001", 12.0), ("EST-001", 44.379)])
    report2.boq.lines[1].unit = "M3"
    monkeypatch.setattr(g, "_fresh_run", lambda *_a, **_k: ([], report2, None))
    with pytest.raises(g.CambioDeCerca):
        g.capture_money(gold_dir, only="x")
    assert g.load_entries(gold_dir)[0].money.concepts["CIM-001"].quantity == 10.0  # type: ignore[union-attr]
    # Un concepto nuevo, no excusado, también es un cambio de lo cercado (antes debía no estar).
    report3 = _report([("CIM-010", 23.0), ("CIM-001", 10.0), ("EST-001", 1.0), ("CIM-002", 1.0)])
    report3.boq.lines[1].unit = "M3"
    monkeypatch.setattr(g, "_fresh_run", lambda *_a, **_k: ([], report3, None))
    with pytest.raises(g.CambioDeCerca):
        g.capture_money(gold_dir, only="x")
    g.capture_money(gold_dir, only="x", acepto=True)
    money = g.load_entries(gold_dir)[0].money
    assert money is not None and money.concepts["CIM-002"].quantity == 1.0
    assert money.concepts["CIM-010"].tolerance_pct == 0.0


def test_capture_estructura_only_its_entry_keeps_reasons_and_transcription(tmp_path, monkeypatch):
    gold_dir = tmp_path / "gold"
    g.save_entry(_entrada(tmp_path, estructura=g.EstructuraExpectation(
        transcripcion="evals/t.json", sin_cerca={"verificaciones.7": "pendiente"})), gold_dir)
    otra = _entrada(tmp_path)
    otra.drawing_id = "y"
    g.save_entry(otra, gold_dir)
    antes_y = (gold_dir / "y.json").read_bytes()
    est = _est({"pilote": {"hojas": {"ES-000": 23}, "campos": {"con_definicion": 23,
                                                             "criticos_total": 92,
                                                             "criticos_del_plano": 69}}},
               {"7/bloquea": [["P-4"]], "2/aviso": [["P-2"]]})  # fmt: skip
    monkeypatch.setattr(g, "_fresh_run", lambda *_a, **_k: ([], None, est))
    g.capture_estructura(gold_dir, "x", acepto=True)
    assert (gold_dir / "y.json").read_bytes() == antes_y
    again = next(e for e in g.load_entries(gold_dir) if e.drawing_id == "x").estructura
    assert again is not None
    assert again.por_familia["pilote"]["criticos_del_plano"] == 69
    assert again.por_hoja == {"pilote": {"ES-000": 23}}
    assert again.verificaciones == {"2/aviso": 1} and again.hallazgos == {"2/aviso": ["P-2"]}
    assert again.sin_cerca == {"verificaciones.7": "pendiente"}
    assert again.transcripcion == "evals/t.json"
    # Lo excusado puede moverse sin --acepto; lo cercado, no.
    est["verificaciones"] += [{"numero": 7, "severidad": "duda", "marcas": ["P-5"]}]
    g.capture_estructura(gold_dir, "x")
    est["elementos"] = est["elementos"][:-1]
    est["resumen"][0]["colocaciones"] = 22
    with pytest.raises(g.CambioDeCerca):
        g.capture_estructura(gold_dir, "x")


def test_cli_refuses_to_recapture_an_existing_id_and_estructura_needs_only(tmp_path, capsys):
    gold_dir = tmp_path / "gold"
    g.save_entry(_entrada(tmp_path, notes="verificado"), gold_dir)
    rc = g.main(["capture", str(tmp_path / "src"), "--id", "x", "--gold", str(gold_dir)])
    assert rc == 2 and "--acepto" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        g.main(["estructura", "--gold", str(gold_dir)])


def test_score_transcripcion_both_directions(tmp_path):
    from klave_engine.evals.gold import score_transcripcion

    path = tmp_path / "t.json"

    def escribir(lecturas, dudas=()):
        path.write_text(json.dumps({"revisado_por": "x", "revisado_en": "2026-10-18",
                                    "lecturas": lecturas, "dudas": list(dudas)}))  # fmt: skip

    k4: dict = {"marca": "K-4", "hoja": "ES-400", "textos": ["6#4", "EYG#3@15"],
          "longitudinal": "6#4", "estribos": "EYG#3@15", "seccion_cm": [30, 15]}
    k5: dict = {"marca": "K5", "hoja": "ES-400", "textos": [], "longitudinal": "6#4",
          "estribos": None, "seccion_cm": None}
    escribir([k4, k5], [{"marca": "K-9", "hoja": "ES-400", "motivo": "dos lecturas"}])
    L = "f.dxf#frame_18"
    specs: list[dict] = [
        {"mark": "K-4", "hoja": "ES-400", "hoja_llave": L, "source": "detalle", "rebar": "6#4",
         "stirrups": "EYG#3@15", "section_cm": None},
        {"mark": "K-4", "hoja": "ES-400", "hoja_llave": L, "source": "detalle", "rebar": None,
         "stirrups": None, "section_cm": [15, 30]},
        {"mark": "K-5", "hoja": "ES-400", "hoja_llave": L, "source": "cuadro", "rebar": "6 #4",
         "stirrups": None, "section_cm": None},
        {"mark": "K-9", "hoja": "ES-400", "hoja_llave": L, "source": "detalle", "rebar": "4#6",
         "stirrups": None, "section_cm": None},
        {"mark": "K-7", "hoja": "ES-400", "hoja_llave": L, "source": "ia", "rebar": "4#4",
         "stirrups": None, "section_cm": None},
    ]
    assert score_transcripcion(path, {"specs": specs}) == (True, [])
    otro: list[dict] = [dict(s) for s in specs]
    otro[0]["stirrups"] = "E#3@15"
    ok, diffs = score_transcripcion(path, {"specs": otro})
    assert not ok and "K-4 en ES-400, estribos" in diffs[0]
    mas = specs + [{"mark": "K-8", "hoja": "ES-400", "hoja_llave": L, "source": "detalle",
                    "rebar": "8#4", "stirrups": None, "section_cm": None}]
    ok, diffs = score_transcripcion(path, {"specs": mas})
    assert not ok and diffs == ["K-8 en ES-400: el motor la lee y la transcripción no la tiene"]
    ok, diffs = score_transcripcion(path, {"specs": specs[:2] + specs[3:]})
    assert not ok and diffs == ["K-5 en ES-400: la transcripción la lee y el motor no"]
    assert score_transcripcion(path, None)[0] is False
    # Una lectura repetida en la transcripción es un error, no se pisa callada.
    escribir([k4, k5, dict(k4, longitudinal="4#4")])
    ok, diffs = score_transcripcion(path, {"specs": specs[:3]})
    assert not ok and diffs == ["K-4 en ES-400: la transcripción la lee dos veces"]
    # Dos marcos con el mismo código: por su hoja_llave, y sin ella no se adivina.
    dos = specs[:3] + [dict(specs[2], hoja_llave="f.dxf#frame_19", rebar="8#4")]
    escribir([k4, k5])
    ok, diffs = score_transcripcion(path, {"specs": dos})
    assert not ok and any("la llevan 2 marcos" in d for d in diffs)
    escribir([dict(k4, hoja_llave=L), dict(k5, hoja_llave=L),
              dict(k5, hoja_llave="f.dxf#frame_19", longitudinal="8#4")])
    assert score_transcripcion(path, {"specs": dos}) == (True, [])
    # Las variantes de una marca por el espesor de su muro (CI), una lectura por variante.
    ci = [{"mark": "CI", "hoja": "ES-200", "hoja_llave": "f.dxf#frame_10", "source": "detalle",
           "rebar": r, "stirrups": "E#2@15", "section_cm": s, "para_muro_cm": m}
          for r, s, m in (("4#3", [20, 20], 20.0), ("6#3", [30, 20], 30.0))]
    escribir([{"marca": "CI", "hoja": "ES-200", "longitudinal": "4#3", "estribos": "E#2@15",
               "seccion_cm": [20, 20], "para_muro_cm": 20},
              {"marca": "CI", "hoja": "ES-200", "longitudinal": "6#3", "estribos": "E#2@15",
               "seccion_cm": [30, 20], "para_muro_cm": 30}])  # fmt: skip
    assert score_transcripcion(path, {"specs": ci}) == (True, [])
    escribir([{"marca": "CI", "hoja": "ES-200", "longitudinal": "4#3", "estribos": "E#2@15",
               "seccion_cm": [20, 20], "para_muro_cm": 20}])
    ok, diffs = score_transcripcion(path, {"specs": ci})
    assert not ok and diffs == ["CI en ES-200 (muros de 30 cm): el motor la lee y la transcripción "
                                "no la tiene"]
