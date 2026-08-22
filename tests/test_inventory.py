"""Levantamiento: symbols counted by name and layer, runs summed by layer in
metres, annotation left out, split per planta when the sheet has frames."""

import ezdxf
from klave_engine.detection.frames import detect_frames
from klave_engine.detection.inventory import (
    build_inventory,
    guess_discipline,
    reads_as_structure,
)
from klave_engine.dxf.parser import DxfParser
from klave_engine.dxf.units import DrawingUnits


def _entities(tmp_path, name, build):
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    build(doc)
    path = tmp_path / name
    doc.saveas(path)
    return DxfParser().parse_file(path).entities


def test_symbols_and_runs_per_sheet(tmp_path):
    def build(doc):
        for name in ("SALIDA-SAN", "LUMINARIA", "PIE DE PLANO 1 125", "N"):
            doc.blocks.new(name=name).add_circle((0, 0), 0.1)
        msp = doc.modelspace()
        for i in range(3):
            msp.add_blockref("SALIDA-SAN", (1 + i, 1), dxfattribs={"layer": "00-SANITARIA"})
        msp.add_blockref("LUMINARIA", (5, 5), dxfattribs={"layer": "ELEC-LUM"})
        msp.add_blockref("PIE DE PLANO 1 125", (40, 0), dxfattribs={"layer": "PIE DE PLANO"})
        msp.add_blockref("N", (0, 20), dxfattribs={"layer": "UBICA"})
        msp.add_line((0, 0), (12, 0), dxfattribs={"layer": "00-SANITARIA"})
        msp.add_lwpolyline([(0, 2), (4, 2), (4, 5)], dxfattribs={"layer": "00-SANITARIA"})
        msp.add_line((0, 10), (3, 10), dxfattribs={"layer": "COTAS1"})  # annotation
        msp.add_line((0, 11), (0.4, 11), dxfattribs={"layer": "GAS"})  # under 1 m: noise
        msp.add_lwpolyline([(20, 0), (24, 0), (24, 3), (20, 3)], close=True,
                           dxfattribs={"layer": "A-PISOS"})  # 12 m² of piso
        msp.add_lwpolyline([(20, 5), (20.4, 5), (20.4, 5.4), (20, 5.4)], close=True,
                           dxfattribs={"layer": "A-PISOS"})  # 0.16 m²: noise
        msp.add_text("TUBERÍA DE PEAD 19MM", height=0.1).set_placement((1, 12))
        for i, tag in enumerate(("V-1", "V-1", "V-2", "P-1", "P-1", "P-1", "T-9")):
            msp.add_text(tag, height=0.1).set_placement((1 + i, 14))
        msp.add_text("N-3", height=0.1).set_placement((9, 14))  # a level marker, not a tag

    entities = _entities(tmp_path, "05 SANITARIO.dxf", build)
    inventory = build_inventory(
        entities, DrawingUnits(unit="m", source="declared", confidence=1.0), []
    )
    assert len(inventory.sheets) == 1
    sheet = inventory.sheets[0]
    assert sheet.discipline == "sanitaria"
    assert [(b.block_name, b.layer, b.count) for b in sheet.blocks] == [
        ("SALIDA-SAN", "00-SANITARIA", 3), ("LUMINARIA", "ELEC-LUM", 1),
    ]
    assert [(r.layer, r.length_m, r.segments) for r in sheet.runs] == [
        ("00-SANITARIA", 19.0, 2), ("A-PISOS", 15.6, 2),
    ]
    assert [(a.layer, a.area_m2, a.count) for a in sheet.areas] == [("A-PISOS", 12.16, 2)]
    assert sheet.specs == ["TUBERÍA DE PEAD 19MM"]
    # Tags repeated at least twice are element types; T-9 alone is a detail title.
    assert [(t.tag, t.count) for t in sheet.tags] == [("P-1", 3), ("V-1", 2)]
    assert "no es una cantidad" in inventory.notes[0]


def test_runs_split_per_planta_with_frames(tmp_path):
    def build(doc):
        doc.blocks.new(name="SALIDA").add_circle((0, 0), 0.1)
        msp = doc.modelspace()
        for x, code, title in ((0, "IS-100", "PLANTA BAJA"), (50, "IS-200", "PLANTA ALTA")):
            msp.add_lwpolyline([(x, 0), (x + 44, 0), (x + 44, 29.4), (x, 29.4)], close=True)
            msp.add_lwpolyline([(x + 38, 0), (x + 44, 0), (x + 44, 29.4), (x + 38, 29.4)],
                               close=True)
            msp.add_text(code, height=0.33).set_placement((x + 38.3, 0.3))
            msp.add_text(title, height=0.12).set_placement((x + 38.3, 2.0))
            for i in range(45):
                msp.add_line((x + 2 + i * 0.5, 20), (x + 2 + i * 0.5, 24),
                             dxfattribs={"layer": "EJES"})
            msp.add_line((x + 2, 5), (x + 12, 5), dxfattribs={"layer": "HIDRAULICA"})
            msp.add_blockref("SALIDA", (x + 3, 6), dxfattribs={"layer": "HIDRAULICA"})
        msp.add_blockref("SALIDA", (53, 6), dxfattribs={"layer": "HIDRAULICA"})

    entities = _entities(tmp_path, "04 HIDRAULICO.dxf", build)
    frames = detect_frames(entities)
    assert [f.code for f in frames] == ["IS-100", "IS-200"]
    inventory = build_inventory(
        entities, DrawingUnits(unit="m", source="declared", confidence=1.0), frames
    )
    sheet = inventory.sheets[0]
    run = next(r for r in sheet.runs if r.layer == "HIDRAULICA")
    assert run.length_m == 20.0
    assert run.by_view == {"IS-100 · PLANTA BAJA": 10.0, "IS-200 · PLANTA ALTA": 10.0}
    block = sheet.blocks[0]
    assert block.count == 3
    assert block.by_view == {"IS-100 · PLANTA BAJA": 1, "IS-200 · PLANTA ALTA": 2}
    assert guess_discipline("09 GAS L.04.dwg") == "gas"


def test_structural_detectors_skip_installation_sheets():
    assert reads_as_structure("02 ESTRUCTURAL L.04.dwg")
    assert reads_as_structure("Plano Prueba 1.dxf")  # unknown names are structure
    assert reads_as_structure("01 ARQ L.04.dwg")
    assert not reads_as_structure("05 SANITARIO L.04.dwg")
    assert not reads_as_structure("09 GAS L.04.dwg")
    assert not reads_as_structure("12 CANCELERIA L.04.dwg")
    # Uploaded names are slugified: word boundaries must survive underscores.
    assert guess_discipline("03-09_gas_l_04_-_26_01_15.dwg") == "gas"
    assert guess_discipline("04-08_aa_l_04_-_26_01_15.dwg") == "aire"
    assert not reads_as_structure("01-04_hidraulico_l_04_-_26_01_30.dwg")


def test_tags_come_from_block_attributes_too(tmp_path):
    """Cancelería bubbles carry the tag as an attribute (CANC_ALUM → V-3)."""

    def build(doc):
        block = doc.blocks.new(name="CANC_ALUM")
        block.add_circle((0, 0), 0.3)
        block.add_attdef("TAG", (0, 0), dxfattribs={"height": 0.15})
        msp = doc.modelspace()
        for i, tag in enumerate(("V-1", "V-1", "V-3", "P-2")):
            ref = msp.add_blockref(
                "CANC_ALUM", (2 + i * 3, 2), dxfattribs={"layer": "NOMENCLATURA"}
            )
            ref.add_auto_attribs({"TAG": tag})

    entities = _entities(tmp_path, "12 CANCELERIA.dxf", build)
    inventory = build_inventory(
        entities, DrawingUnits(unit="m", source="declared", confidence=1.0), []
    )
    sheet = inventory.sheets[0]
    assert [(b.block_name, b.count) for b in sheet.blocks] == [("CANC_ALUM", 4)]
    assert [(t.tag, t.count) for t in sheet.tags] == [("V-1", 2), ("P-2", 1), ("V-3", 1)]
