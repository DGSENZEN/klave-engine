"""El registro de disciplinas: quién lee cada hoja.

v1 (espine): el registro es dueño del ruteo y del vocabulario, y reproduce
exactamente la conducta anterior de ``reads_as_structure``. Los detectores
por disciplina se enchufan en el hueco ``detect`` cuando cada suite
aterrice con su gold.
"""

from __future__ import annotations

import re

from klave_engine.detection.disciplines.vocab import SUITES, DisciplineSuite

REGISTRY: dict[str, DisciplineSuite] = {suite.key: suite for suite in SUITES}

_SEPARATORS = re.compile(r"[_\-./]+")


def route_sheet(sheet_label: str) -> DisciplineSuite:
    """La suite que lee esta hoja. Desconocido = estructura: un «Plano
    1.dwg» pelón es el caso común y merece la lectura completa."""
    words = _SEPARATORS.sub(" ", sheet_label or "")
    for suite in SUITES:
        if suite.name_hint.search(words):
            return suite
    return REGISTRY["estructural"]


__all__ = ["REGISTRY", "DisciplineSuite", "route_sheet"]
