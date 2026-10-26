"""La obra didáctica del recorrido: cada cosa que el recorrido señala tiene que
existir en la lectura, en cada corrida, sin IA. Si un cambio del lector borra
una de estas anclas, esta prueba falla antes que el recorrido."""

import json
from pathlib import Path

import pytest
from klave_engine.common import config as config_module
from klave_engine.costing.captura import lo_que_el_plano_no_dio
from klave_engine.costing.catalog_store import get_catalog_store
from klave_engine.costing.hallazgos import diagnose
from klave_engine.costing.presentation import CONFIDENCE_FIRM
from klave_engine.ejemplo.catalogo import sembrar_catalogo_didactico
from klave_engine.ejemplo.obra import build_obra_ejemplo
from klave_engine.pipeline import run_full_pipeline

GOLD = Path(__file__).resolve().parents[1] / "packages" / "klave_engine" / "ejemplo" / "etiquetas_gold.json"


def _procesar(base: Path, revision: str):
    root = base / f"rev_{revision.lower()}"
    build_obra_ejemplo(root, "A")
    if revision == "B":
        build_obra_ejemplo(root, "B")
    store = get_catalog_store(base / "data", workspace_id=f"t_{revision}")
    sembrar_catalogo_didactico(store)
    settings = config_module.get_settings()
    return run_full_pipeline(
        root, settings, catalog_store=store, record_history=False, perfil_del_taller=False
    ), root, settings


@pytest.fixture(scope="module")
def corridas(tmp_path_factory):
    base = tmp_path_factory.mktemp("obra_ejemplo")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("KLAVE_DATA_DIR", str(base / "data"))
        mp.setenv("KLAVE_USERS_DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
        config_module.get_settings.cache_clear()
        try:
            yield {"A": _procesar(base, "A"), "B": _procesar(base, "B")}
        finally:
            config_module.get_settings.cache_clear()


def _etiquetas(result) -> dict[str, list[str]]:
    por_tipo: dict[str, list[str]] = {}
    for d in result.detections:
        por_tipo.setdefault(d.detection_type.value, []).append(d.display_label or d.label)
    return {k: sorted(v) for k, v in sorted(por_tipo.items())}


def test_rev_a_reads_in_centimetres(corridas):
    result, _, _ = corridas["A"]
    assert result.cost_report.boq.units_reliable


def test_rev_a_has_a_doubt_for_the_visor(corridas):
    result, _, _ = corridas["A"]
    assert any(d.confidence < CONFIDENCE_FIRM for d in result.detections)


def test_rev_a_blocks_on_fc_and_flags_money(corridas):
    result, _, _ = corridas["A"]
    hallazgos = diagnose(result.cost_report).hallazgos
    assert any(
        h.severity == "bloqueante" and "f'c" in h.title for h in hallazgos
    ), [(h.severity, h.title) for h in hallazgos]
    assert any(h.severity == "dinero" for h in hallazgos)


def test_rev_a_has_variants_to_map(corridas):
    result, _, _ = corridas["A"]
    assert any(len(line.variants) >= 2 for line in result.cost_report.boq.lines)


def test_rev_a_is_mostly_priced(corridas):
    boq = corridas["A"][0].cost_report.boq
    priced = [line for line in boq.lines if not line.unpriced]
    assert boq.direct_cost_total > 0
    assert len(priced) >= 0.8 * len(boq.lines)
    assert any(line.unpriced for line in boq.lines)  # the deliberate dinero finding


def test_rev_a_has_a_programa(corridas):
    schedule = corridas["A"][0].cost_report.schedule
    assert schedule.total_duration_days > 0 and len(schedule.phases) >= 3


def test_rev_a_has_a_captura_list(corridas):
    result, _, _ = corridas["A"]
    assert lo_que_el_plano_no_dio(result.cost_report, result.detections).total > 0


def test_rev_b_has_aditivas_and_deductivas(corridas):
    antes = {l.concept_code: l.quantity for l in corridas["A"][0].cost_report.boq.lines}
    despues = {l.concept_code: l.quantity for l in corridas["B"][0].cost_report.boq.lines}
    deltas = {c: despues.get(c, 0.0) - antes.get(c, 0.0) for c in set(antes) | set(despues)}
    assert any(v > 0.001 for v in deltas.values()), deltas
    assert any(v < -0.001 for v in deltas.values()), deltas


def test_labels_match_gold(corridas):
    gold = json.loads(GOLD.read_text())
    assert _etiquetas(corridas["A"][0]) == gold["rev_a"]
    assert _etiquetas(corridas["B"][0]) == gold["rev_b"]


def test_no_ai_read_is_involved(corridas):
    for _, root, _ in corridas.values():
        assert not list(root.rglob("ai_read*.json"))
