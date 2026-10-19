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

from klave_engine.evals.gold import EstructuraExpectation, score_estructura  # noqa: E402


def _estructura_like(
    want: EstructuraExpectation, castillo_con_definicion: int | None = None, **extra: int
) -> dict:
    """Un ``estructura.json`` mínimo cuyas tarjetas y hallazgos son los de ``want`` (los
    ``extra`` son ``"numero/severidad"`` → cuántos hallazgos más)."""
    resumen = []
    for familia, campos in want.por_familia.items():
        tarjeta = {"familia": familia, "colocaciones": 0, "con_definicion": 0,
                   "criticos_total": 0, "criticos_del_plano": 0}  # fmt: skip
        tarjeta.update(campos)
        if familia == "castillo" and castillo_con_definicion is not None:
            tarjeta["con_definicion"] = castillo_con_definicion
        resumen.append(tarjeta)
    verificaciones = []
    for clave, n in want.verificaciones.items():
        numero, _, severidad = clave.partition("/")
        verificaciones += [{"numero": int(numero), "severidad": severidad or "duda"}] * n
    for clave, n in extra.items():
        numero, _, severidad = clave.partition("_")
        verificaciones += [{"numero": int(numero.lstrip("v")), "severidad": severidad}] * n
    return {"resumen": resumen, "verificaciones": verificaciones}


def test_estructura_fence_is_exact(tmp_path):
    want = EstructuraExpectation(
        por_familia={"castillo": {"colocaciones": 2, "con_definicion": 2,
                                  "criticos_total": 8, "criticos_del_plano": 6}},
        verificaciones={"8": 1},
    )
    ok, diffs = score_estructura(want, _estructura_like(want))
    assert ok and diffs == []
    ok2, diffs2 = score_estructura(want, _estructura_like(want, castillo_con_definicion=1))
    assert not ok2 and "castillo" in diffs2[0]


def test_estructura_fence_everything_not_fenced_must_be_zero_or_excused():
    want = EstructuraExpectation(
        por_familia={"castillo": {"colocaciones": 2, "con_definicion": 2}},
        verificaciones={"1/bloquea": 1, "2": 1},
        sin_cerca={"por_familia.castillo.criticos_total": "no medido",
                   "verificaciones.7": "pendiente de la transcripción"},
    )
    base = _estructura_like(want)
    assert score_estructura(want, base) == (True, [])
    # Una familia nueva con colocaciones que el gold no conoce: falla.
    nueva = _estructura_like(want)
    nueva["resumen"].append({"familia": "trabe", "colocaciones": 3, "con_definicion": 0,
                             "criticos_total": 12, "criticos_del_plano": 0})
    ok, diffs = score_estructura(want, nueva)
    assert not ok and any("trabe" in d for d in diffs)
    # Un campo no cercado ni excusado de una familia cercada: debe ser 0.
    cp = _estructura_like(want)
    cp["resumen"][0]["criticos_del_plano"] = 1
    ok, diffs = score_estructura(want, cp)
    assert not ok and any("castillo.criticos_del_plano" in d for d in diffs)
    # Lo excusado no se mide: criticos_total y la verificación 7 pueden moverse.
    libre = _estructura_like(want, v7_bloquea=40)
    libre["resumen"][0]["criticos_total"] = 999
    assert score_estructura(want, libre) == (True, [])
    # Una severidad no cercada de una verificación cercada por severidad: debe ser 0.
    ok, diffs = score_estructura(want, _estructura_like(want, v1_aviso=2))
    assert not ok and any("1/aviso" in d for d in diffs)
    # Una verificación cercada por su total cuenta todas sus severidades.
    ok, diffs = score_estructura(want, _estructura_like(want, v2_aviso=1))
    assert not ok and any(d.startswith("verificación 2:") for d in diffs)
    # Una verificación que no aparece en el gold: debe ser 0.
    ok, diffs = score_estructura(want, _estructura_like(want, v11_duda=1))
    assert not ok and any("11" in d for d in diffs)
    # Y una cercada que desaparece también falla (exacta, no «a lo más»).
    falta = _estructura_like(want)
    falta["verificaciones"] = [v for v in falta["verificaciones"] if v["numero"] != 2]
    ok, diffs = score_estructura(want, falta)
    assert not ok and any(d.startswith("verificación 2:") for d in diffs)
    # Lo mismo por severidad: un 1/bloquea cercado que desaparece falla.
    sin_bloquea = _estructura_like(want)
    sin_bloquea["verificaciones"] = [v for v in sin_bloquea["verificaciones"] if v["numero"] != 1]
    ok, diffs = score_estructura(want, sin_bloquea)
    assert not ok and diffs == ["verificación 1/bloquea: esperado 1, motor 0"]


def test_estructura_fence_without_estructura_json_fails():
    want = EstructuraExpectation(por_familia={"castillo": {"colocaciones": 1}})
    ok, diffs = score_estructura(want, None)
    assert not ok and "estructura.json" in diffs[0]


def test_estructura_fence_rejects_unknown_keys():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        EstructuraExpectation(por_familia={"castillo": {"colocacion": 1}})
    with pytest.raises(ValidationError):
        EstructuraExpectation(verificaciones={"1/grave": 1})
    with pytest.raises(ValidationError):
        EstructuraExpectation(sin_cerca={"castillo": "sin prefijo"})


def test_fresh_capture_fences_the_structural_reading_and_evaluation_uses_it(data_dir, tmp_path):
    from klave_engine.evals.gold import render_markdown

    settings = get_settings()
    root = tmp_path / "demo"
    write_demo_project(root)
    entry = capture(root, "demo", settings, fresh=True)
    assert entry.estructura is not None and entry.estructura.transcripcion is None
    # Lo que la corrida del demo dice (y su dibujo, a mano: 3 etiquetas de columna, 1 de trabe,
    # 2 contornos de zapata sin marca; nada definido).
    assert entry.estructura.por_familia["columna"]["colocaciones"] == 3
    assert entry.estructura.por_familia["zapata"]["con_definicion"] == 0
    ok = evaluate_entry(entry, settings)
    assert ok.passed and ok.estructura_passed is True and ok.estructura_diffs == []

    movida = entry.model_copy(deep=True)
    assert movida.estructura is not None
    movida.estructura.por_familia["columna"]["colocaciones"] = 4
    movida.estructura.verificaciones["7/duda"] = 0
    bad = evaluate_entry(movida, settings)
    assert not bad.passed and bad.estructura_passed is False
    assert any(d.startswith("columna.colocaciones") for d in bad.estructura_diffs)
    assert any(d.startswith("verificación 7/duda") for d in bad.estructura_diffs)
    md = render_markdown({"evaluated_at": "x", "all_passed": False, "entries": [bad.model_dump()]})
    assert "### Lectura estructural" in md and "columna.colocaciones" in md

    # Excusar lo que se movió, con su razón, vuelve a pasar; y sin cerca no se mide nada.
    excusada = movida.model_copy(deep=True)
    assert excusada.estructura is not None
    excusada.estructura.sin_cerca = {
        "por_familia.columna.colocaciones": "prueba", "verificaciones.7/duda": "prueba",
    }
    del excusada.estructura.por_familia["columna"]["colocaciones"]
    del excusada.estructura.verificaciones["7/duda"]
    assert evaluate_entry(excusada, settings).passed
    sin = entry.model_copy(deep=True)
    sin.estructura = None
    out = evaluate_entry(sin, settings)
    assert out.passed and out.estructura_passed is None


def test_estructura_from_json_drops_what_is_excused():
    from klave_engine.evals.gold import estructura_from_json

    est = {
        "resumen": [
            {"familia": "castillo", "colocaciones": 2, "con_definicion": 2, "criticos_total": 8,
             "criticos_del_plano": 5},
            {"familia": "zapata", "colocaciones": 3, "con_definicion": 0, "criticos_total": 9,
             "criticos_del_plano": 0},
            {"familia": "general", "colocaciones": 0, "con_definicion": 0, "criticos_total": 0,
             "criticos_del_plano": 0},
        ],
        "verificaciones": [{"numero": 7, "severidad": "duda"}, {"numero": 1, "severidad": "aviso"},
                           {"numero": 1, "severidad": "bloquea"}],
    }
    razones = {"por_familia.zapata": "r", "por_familia.castillo.criticos_del_plano": "r",
               "verificaciones.7": "r", "verificaciones.1/aviso": "r"}
    want = estructura_from_json(est, razones)
    assert want is not None
    assert want.por_familia == {"castillo": {"colocaciones": 2, "con_definicion": 2,
                                             "criticos_total": 8}}
    assert want.verificaciones == {"1/bloquea": 1}
    assert want.sin_cerca == razones
    assert score_estructura(want, est) == (True, [])
    full = estructura_from_json(est)
    assert full.verificaciones == {"1/bloquea": 1, "1/aviso": 1, "7/duda": 1}
    assert "general" not in full.por_familia and score_estructura(full, est) == (True, [])


def _report(lines):
    from klave_engine.costing.models import BoqLine, CostReport

    boq = [BoqLine.model_construct(concept_code=c, quantity=q, unit="PZA", variants=[],
                                   unpriced=True) for c, q in lines]  # fmt: skip
    report = CostReport.model_construct()
    report.boq = type("B", (), {"lines": boq, "direct_cost_total": 10.0})()
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


def test_capture_money_keeps_exclusions_tolerance_and_note(tmp_path, monkeypatch):
    from datetime import UTC, datetime

    from klave_engine.evals import gold as g

    gold_dir = tmp_path / "gold"
    (tmp_path / "src" / "drawings").mkdir(parents=True)
    entry = g.GoldEntry(
        drawing_id="x", source=str(tmp_path / "src"), files={}, status="baseline",
        captured_at=datetime(2026, 10, 18, tzinfo=UTC),
        money=g.MoneyExpectation(
            concepts={"CIM-010": g.QuantityExpectation(quantity=20, unit="PZA", tolerance_pct=0.0,
                                                       note="contado en crudo")},
            sin_cerca={"EST-001": "storey", "costo_directo": "no verificado"},
        ),
    )
    g.save_entry(entry, gold_dir)
    report = _report([("CIM-010", 23.0), ("EST-001", 44.379)])
    monkeypatch.setattr(g, "_fresh_run", lambda *_a, **_k: ([], report, None))
    g.capture_money(gold_dir, only="x")
    again = g.load_entries(gold_dir)[0].money
    assert again is not None
    assert again.concepts["CIM-010"].quantity == 23.0
    assert again.concepts["CIM-010"].tolerance_pct == 0.0
    assert again.concepts["CIM-010"].note == "contado en crudo"
    assert "EST-001" not in again.concepts and again.direct_cost is None
    assert again.sin_cerca == {"EST-001": "storey", "costo_directo": "no verificado"}


def test_capture_estructura_keeps_reasons_and_transcription(tmp_path, monkeypatch):
    from datetime import UTC, datetime

    from klave_engine.evals import gold as g

    gold_dir = tmp_path / "gold"
    (tmp_path / "src" / "drawings").mkdir(parents=True)
    entry = g.GoldEntry(
        drawing_id="x", source=str(tmp_path / "src"), files={}, status="baseline",
        captured_at=datetime(2026, 10, 18, tzinfo=UTC),
        estructura=g.EstructuraExpectation(transcripcion="evals/t.json",
                                           sin_cerca={"verificaciones.7": "pendiente"}),
    )
    g.save_entry(entry, gold_dir)
    est = {"resumen": [{"familia": "pilote", "colocaciones": 23, "con_definicion": 23,
                        "criticos_total": 92, "criticos_del_plano": 69}],
           "verificaciones": [{"numero": 7, "severidad": "bloquea"},
                              {"numero": 2, "severidad": "aviso"}]}
    monkeypatch.setattr(g, "_fresh_run", lambda *_a, **_k: ([], None, est))
    g.capture_estructura(gold_dir, only="x")
    again = g.load_entries(gold_dir)[0].estructura
    assert again is not None
    assert again.por_familia["pilote"]["criticos_del_plano"] == 69
    assert again.verificaciones == {"2/aviso": 1}
    assert again.sin_cerca == {"verificaciones.7": "pendiente"}
    assert again.transcripcion == "evals/t.json"


def test_score_transcripcion_both_directions(tmp_path):
    import json

    from klave_engine.evals.gold import score_transcripcion

    path = tmp_path / "t.json"
    path.write_text(json.dumps({
        "revisado_por": "x", "revisado_en": "2026-10-18",
        "lecturas": [
            {"marca": "K-4", "hoja": "ES-400", "textos": ["6#4", "EYG#3@15"],
             "longitudinal": "6#4", "estribos": "EYG#3@15", "seccion_cm": [30, 15]},
            {"marca": "K5", "hoja": "ES-400", "textos": [], "longitudinal": "6#4",
             "estribos": None, "seccion_cm": None},
        ],
        "dudas": [{"marca": "K-9", "hoja": "ES-400", "motivo": "dos lecturas"}],
    }))
    specs: list[dict] = [
        {"mark": "K-4", "hoja": "ES-400", "source": "detalle", "rebar": "6#4",
         "stirrups": "EYG#3@15", "section_cm": None},
        {"mark": "K-4", "hoja": "ES-400", "source": "detalle", "rebar": None, "stirrups": None,
         "section_cm": [15, 30]},
        {"mark": "K-5", "hoja": "ES-400", "source": "cuadro", "rebar": "6 #4", "stirrups": None,
         "section_cm": None},
        {"mark": "K-9", "hoja": "ES-400", "source": "detalle", "rebar": "4#6", "stirrups": None,
         "section_cm": None},
        {"mark": "K-7", "hoja": "ES-400", "source": "ia", "rebar": "4#4", "stirrups": None,
         "section_cm": None},
    ]
    assert score_transcripcion(path, {"specs": specs}) == (True, [])
    # El motor lee algo distinto: falla con la marca y el campo.
    otro: list[dict] = [dict(s) for s in specs]
    otro[0]["stirrups"] = "E#3@15"
    ok, diffs = score_transcripcion(path, {"specs": otro})
    assert not ok and "K-4 en ES-400, estribos" in diffs[0]
    # El motor lee una marca que la transcripción no tiene (y no es IA): falla.
    mas = specs + [{"mark": "K-8", "hoja": "ES-400", "source": "detalle", "rebar": "8#4",
                    "stirrups": None, "section_cm": None}]
    ok, diffs = score_transcripcion(path, {"specs": mas})
    assert not ok and diffs == ["K-8 en ES-400: el motor la lee y la transcripción no la tiene"]
    # La transcripción lee una marca que el motor no: falla.
    ok, diffs = score_transcripcion(path, {"specs": specs[:2] + specs[3:]})
    assert not ok and diffs == ["K-5 en ES-400: la transcripción la lee y el motor no"]
    assert score_transcripcion(path, None)[0] is False
