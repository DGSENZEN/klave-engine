"""Tarea 9c, sobre el plano estructural de Marina (si está): los títulos de detalle y el armado de
sus secciones, medidos contra la verdad del dibujo (cada texto por su handle del DXF).

- R164: una caja reclamada es la sección PROPIA del título; T3-8 ya no reclama el escalón de la
  losa vecina; T2-7 (sección compuesta) recupera su caja y su armado.
- Las atribuciones «posible» equivocadas de la tarea 9 (R164, la carga de la tarea 9) nunca se
  vuelven una lectura bajo el título equivocado."""

from pathlib import Path

import pytest
from klave_engine.detection.frames import detect_frames
from klave_engine.detection.schedules import ScheduleInventory, build_schedule_inventory
from klave_engine.detection.text_patterns import TextPatternConfig
from klave_engine.dxf.harmonize import harmonize_units
from klave_engine.dxf.parser import DxfParser

C = TextPatternConfig()
_MARINA = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "raw"
    / "marina-4"
    / "converted"
    / "02 ESTRUCTURAL L.04 - 26.01.15.dxf"
)


@pytest.fixture(scope="module")
def marina() -> tuple[ScheduleInventory, dict[str, str]]:
    """El inventario de Marina y, por handle del DXF, el id de su entidad."""
    if not _MARINA.exists():
        pytest.skip(f"sin el dibujo {_MARINA.name}")
    dibujo = DxfParser().parse_file(_MARINA)
    unidades, _ = harmonize_units([(dibujo.source_file, dibujo.insunits, dibujo.entities)])
    inv = build_schedule_inventory(
        dibujo.entities, C, unit_to_m=unidades.to_meters(), frames=detect_frames(dibujo.entities)
    )
    return inv, {e.raw_handle: e.entity_id for e in dibujo.entities}


def _posibles(inv: ScheduleInventory, entidad: str) -> list[str]:
    return sorted({m for r in inv.rechazos if r.entidad_id == entidad for m in r.posibles})


def _leida_por(inv: ScheduleInventory, entidad: str) -> set[str]:
    """Las marcas cuyas lecturas (no la IA) toman el texto."""
    return {s.mark for s in inv.specs if s.source != "ia" and entidad in s.entidades}


# T2-7 (ES-201), su armado propio (R164): «2#6» con su flecha al cuerpo, lo de su alzado («2#8»,
# los dos «4#8», «1@6,8@15») y sus «2E#4».
_DE_T2_7 = ["A9E0B", "A99A3", "A99A2", "A99A8", "AEBDC", "A9AAA", "A9A22"]


@pytest.mark.parametrize("handle", _DE_T2_7)
def test_t2_7_composite_section_keeps_its_own_armado(marina, handle):
    inv, ids = marina
    entidad = ids[handle]
    assert "T2-7" in _posibles(inv, entidad)
    assert _leida_por(inv, entidad) == set()  # su caja es reclamada: nunca se lee


@pytest.mark.parametrize("handle", ["A903A", "A903B", "A903C", "A9031"])
def test_t3_8_no_longer_claims_the_slab_step(marina, handle):
    # R164: el escalón de la losa nervada junto a T3-8 (ES-301) no es su sección: lo que va en él
    # no es de T3-8.
    inv, ids = marina
    entidad = ids[handle]
    assert "T3-8" not in _posibles(inv, entidad)
    assert "T3-8" not in _leida_por(inv, entidad)


# Atribuciones «posible» equivocadas de la tarea 9 (R164 y la carga de la tarea 9): bloqueos, nunca
# lecturas. Ninguna se lee bajo el título equivocado (bajo el suyo, o sin leer).
_EQUIVOCADAS = [
    ("BD465", "T1-8"),  # «3#8» del alzado de T1-7
    ("CFC1F", "CTA-14"),  # renglones de columna
    ("8F6B6", "T3-5"),
    ("8F6BA", "T3-10"),
    ("8F9F0", "T3-11"),
    ("A9A23", "T2-11"),
    ("CCE7C", "CTA-7"),
    ("D0949", "CTA-16"),
    ("8F9F2", "T3-10"),  # alzado de T3-9
    ("8F9F3", "T3-10"),
    ("8F9F4", "T3-10"),
    ("8FD34", "T3-14"),  # alzado de T3-13
    ("8FD71", "T3-14"),
    ("BAFC2", "Z1"),  # alzado de W2
    ("AC7AD", "T2-14"),  # alzado de T2-13
    ("A903A", "T3-8"),  # el escalón de la losa junto a T3-8
    ("A903B", "T3-8"),
    ("A903C", "T3-8"),
    ("A9031", "T3-8"),
    ("8F326", "T3-7"),  # «2#8» de T3-3
    ("8F328", "T3-7"),  # «@20» de T3-3
    ("8F62C", "T3-7"),  # «10@10,1@6» de T3-6
    ("BB1C6", "T1-7"),  # «1#4» de W1
    ("BB1C4", "T1-7"),  # «2#4» de W1
    ("D04F2", "CTA-13"),  # «3#8» de CTA-16
    ("4B767", "T3-3"),  # «E#4» de T3-1
    ("8F1A7", "T3-3"),  # «1@6» de T3-1
    ("B79B6", "CE-3"),  # «E#2@15» de CE-1 (ES-100)
    ("B79E7", "CE-3"),  # «E#2@15» de CE-2 (ES-100)
]


@pytest.mark.parametrize("handle,equivocada", _EQUIVOCADAS)
def test_a_wrong_posible_is_never_read_under_the_wrong_title(marina, handle, equivocada):
    inv, ids = marina
    assert equivocada not in _leida_por(inv, ids[handle])
