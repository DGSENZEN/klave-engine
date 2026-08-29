"""El registro de disciplinas: quién lee cada hoja.

v1 (espine): el registro es dueño del ruteo y del vocabulario, y reproduce
exactamente la conducta anterior de ``reads_as_structure``. Los detectores
por disciplina se enchufan en el hueco ``detect`` cuando cada suite
aterrice con su gold.
"""

from __future__ import annotations

import re
from dataclasses import replace

from klave_engine.detection.disciplines import hidrosanitaria
from klave_engine.detection.disciplines.vocab import SUITES, DisciplineSuite

# Qué suite llenó su hueco ``detect``. Las demás siguen con el cableado por
# default de suite.py hasta que aterricen con su propio gold.
_DETECTORS = {
    "hidraulica": hidrosanitaria.detect,
    "sanitaria": hidrosanitaria.detect,
}

SUITES_WIRED: tuple[DisciplineSuite, ...] = tuple(
    replace(suite, detect=_DETECTORS[suite.key]) if suite.key in _DETECTORS else suite
    for suite in SUITES
)

REGISTRY: dict[str, DisciplineSuite] = {suite.key: suite for suite in SUITES_WIRED}

_SEPARATORS = re.compile(r"[_\-./]+")


def route_sheet(sheet_label: str) -> DisciplineSuite:
    """La suite que lee esta hoja. Desconocido = estructura: un «Plano
    1.dwg» pelón es el caso común y merece la lectura completa."""
    words = _SEPARATORS.sub(" ", sheet_label or "")
    for suite in SUITES_WIRED:
        if suite.name_hint.search(words):
            return suite
    return REGISTRY["estructural"]


# El voto exige mayoría clara: un ganador con pocos trazos, o con un
# segundo lugar cerca, no dice nada — los nombres de capa se repiten
# entre disciplinas y un empate no es evidencia.
VOTE_MIN_HITS = 20
VOTE_MIN_MARGIN = 3.0


def vote_content(entities) -> tuple[str, int] | None:
    """La disciplina que el contenido de la hoja vota, o None sin mayoría.

    Cuenta entidades cuya capa (o bloque) casa con el vocabulario de cada
    suite. v1 solo avisa cuando contradice al nombre; el reruteo espera a
    que cada suite tenga su gold."""
    from klave_engine.detection.results import layer_matches

    hits: dict[str, int] = {}
    for entity in entities:
        layer = getattr(entity, "layer", "") or ""
        block = getattr(entity, "block_name", "") or ""
        for suite in SUITES:
            if suite.layer_hints and layer_matches(layer, list(suite.layer_hints)):
                hits[suite.key] = hits.get(suite.key, 0) + 1
                break
            if suite.block_hints and block and layer_matches(block, list(suite.block_hints)):
                hits[suite.key] = hits.get(suite.key, 0) + 1
                break
    if not hits:
        return None
    ranked = sorted(hits.items(), key=lambda kv: kv[1], reverse=True)
    winner, count = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0
    if count < VOTE_MIN_HITS or (runner_up and count < VOTE_MIN_MARGIN * runner_up):
        return None
    return (winner, count)


__all__ = ["REGISTRY", "DisciplineSuite", "route_sheet", "vote_content"]
