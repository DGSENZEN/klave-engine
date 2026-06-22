"""Dimension-text inventory tests."""

from klave_engine.detection.dimensions import build_dimension_inventory, parse_block_name
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.graph.evidence import EvidencePacket


def _text(value: str, idx: int = 0) -> NormalizedEntity:
    return NormalizedEntity(
        entity_id=f"e{idx}",
        entity_type=EntityType.text,
        source_file="s.dxf",
        layer="TEXTOS",
        bbox=(0, 0, 1, 1),
        raw_handle="H",
        text=value,
        properties={"height": 0.1},
        evidence=EvidencePacket(source="s.dxf", method="t"),
    )


def test_sections_blocks_and_thickness() -> None:
    ents = [
        _text("DALA 15x30", 1),
        _text("CASTILLO 15x30", 2),
        _text("COLUMNA 30x40", 3),
        _text("MURO DE BLOCK 15x20x40", 4),
        _text("MURO DE CARGA 15 CM", 5),
        _text("LOSA H=20", 6),
        _text("LOSA DE VIGUETA Y BOVEDILLA 12-5", 7),
        _text("2#4, E#3@20", 8),
    ]
    inv = build_dimension_inventory(ents)
    # 15x30 appears twice → most common → typical
    assert inv.typical_section_cm == (15, 30)
    assert inv.typical_section_m2 == 0.045
    # block 15x20x40 must not be double-counted as a 15x20 section
    assert "15x20x40" in inv.block_specs
    assert "15x20" not in inv.sections_cm
    assert inv.typical_wall_thickness_cm == 15
    assert inv.typical_peralte_cm == 20
    assert inv.vigueta_system == "12-5"
    assert "#3@20" in inv.rebar_calls


def test_implausible_sections_filtered() -> None:
    inv = build_dimension_inventory([_text("ESC 1x100", 1), _text("nota 6x6", 2)])
    # 1x100 and 6x6 are outside plausible structural bounds → no typical section
    assert inv.typical_section_cm is None


def test_wall_thickness_falls_back_to_block_width() -> None:
    inv = build_dimension_inventory([_text("MURO DE BLOCK 12x20x40", 1)])
    assert inv.typical_wall_thickness_cm == 12  # block width, no explicit 'N CM'


def test_empty_inventory_has_note() -> None:
    inv = build_dimension_inventory([_text("PLANO ESTRUCTURAL", 1)])
    assert inv.typical_section_cm is None
    assert inv.notes


# --- block-name semantics & DIMENSION ingestion -------------------------------


def test_parse_block_name_revit_families() -> None:
    wall = parse_block_name("Muro básico _ Hormigón con cimentación - 30 cm - ___-650045")
    assert wall.element_class == "muro"
    assert wall.thickness_cm == 30
    mull = parse_block_name("Montante rectangular - 5x10 cm negro-445514")
    assert mull.element_class == "montante"
    assert mull.section_cm == (5, 10)
    lvl = parse_block_name("Nivel - Extremo de nivel-1605-Sección 2")
    assert lvl.is_level_marker and lvl.element_class == "nivel"
    assert parse_block_name("TICK").element_class is None


def _dim(value_m: float, idx: int) -> NormalizedEntity:
    return NormalizedEntity(
        entity_id=f"d{idx}",
        entity_type=EntityType.dimension,
        source_file="s.dxf",
        layer="COTAS",
        bbox=(0, 0, value_m, 0),
        raw_handle="H",
        properties={"measurement": value_m},
        evidence=EvidencePacket(source="s.dxf", method="t"),
    )


def _insert(name: str, idx: int) -> NormalizedEntity:
    return NormalizedEntity(
        entity_id=f"i{idx}",
        entity_type=EntityType.insert,
        source_file="s.dxf",
        layer="0",
        bbox=(0, 0, 1, 1),
        raw_handle="H",
        block_name=name,
        properties={},
        evidence=EvidencePacket(source="s.dxf", method="t"),
    )


def test_inventory_ingests_dimensions_and_blocks() -> None:
    ents = [
        _dim(0.30, 1), _dim(0.30, 2), _dim(0.90, 3),  # 0.90 m is a spacing
        _dim(5.0, 4),  # 500 cm out of element range → ignored
        _insert("Nivel - Extremo de nivel", 5),
        _insert("Muro básico Hormigón - 20 cm", 6),
    ]
    inv = build_dimension_inventory(ents, meters_factor=1.0)
    assert inv.dimension_count == 4
    assert inv.measured_dimensions_cm.get(30) == 2
    assert inv.measured_dimensions_cm.get(90) == 1
    assert 500 not in inv.measured_dimensions_cm  # out of member-scale range
    assert inv.level_marker_count == 1
    assert inv.block_classes.get("muro") == 1
    # no NxM text and no explicit 'N CM' text → wall thickness from block name
    assert inv.typical_wall_thickness_cm == 20
    assert inv.typical_wall_thickness_source == "nombre de bloque"
