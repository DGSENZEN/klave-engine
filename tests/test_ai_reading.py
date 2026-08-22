"""AI reading of sheet images: renders per frame, readings with provenance,
specs that only fill what the rules did not read."""

import ezdxf
from klave_engine.common.io import write_json
from klave_engine.detection.frames import detect_frames
from klave_engine.detection.schedules import (
    ElementSpec,
    ScheduleInventory,
    merge_external_specs,
)
from klave_engine.dxf.parser import DxfParser
from klave_engine.llm.reader import ElementRead, SheetRead, read_frames
from klave_engine.llm.render import render_region
from klave_engine.llm.service import (
    AiReads,
    ai_element_specs,
    load_ai_reads,
    run_ai_reading,
)


def _frame(msp, x, y, code, title, w=44.0, h=29.4):
    msp.add_lwpolyline([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], close=True)
    sx = x + w - 5.7
    msp.add_lwpolyline([(sx, y), (x + w, y), (x + w, y + h), (sx, y + h)], close=True)
    msp.add_text(code, height=0.33).set_placement((sx + 0.3, y + 0.3))
    msp.add_text(title, height=0.12).set_placement((sx + 0.3, y + 2.0))
    for i in range(45):
        msp.add_line((x + 2 + i * 0.5, y + 20), (x + 2 + i * 0.5, y + 24))
    msp.add_text("K-1 15x20 4#3 E#2@20", height=0.15).set_placement((x + 5, y + 10))


def _project(tmp_path):
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    _frame(msp, 0, 0, "ES-100", "PLANTA DE CIMENTACIÓN")
    _frame(msp, 50, 0, "ES-101", "DETALLES DE ESTRUCTURA")
    path = tmp_path / "sheet.dxf"
    doc.saveas(path)
    entities = DxfParser().parse_file(path).entities
    frames = detect_frames(entities)
    artifact = tmp_path / "run"
    artifact.mkdir()
    write_json(artifact / "normalized_entities.json", entities)
    write_json(artifact / "frames.json", frames)
    control = tmp_path / "processed"
    control.mkdir()
    return entities, frames, artifact, control


def test_render_draws_linework_and_text(tmp_path):
    entities, frames, _a, _c = _project(tmp_path)
    rendered = render_region(entities, frames[0].bbox, long_side_px=800)
    assert rendered.width == 800 and rendered.png[:8] == b"\x89PNG\r\n\x1a\n"
    assert rendered.entity_count > 40


def test_ai_reading_job_persists_readings_with_provenance(tmp_path):
    _e, _f, artifact, control = _project(tmp_path)
    seen: list[str] = []

    def fake_reader(png: bytes, prompt: str):
        seen.append(prompt)
        assert png[:4] == b"\x89PNG"
        if "ES-101" in prompt:
            raise RuntimeError("rate limited")
        return (
            SheetRead(
                sheet_code="ES-100", title="PLANTA DE CIMENTACIÓN", level="CIMENTACIÓN",
                concrete_fc={"cimentacion": 250},
                elements=[ElementRead(mark="K-1", family="castillo", section_cm="15x20",
                                      rebar="4#3", stirrups="E#2@20", confidence=0.9)],
            ),
            {"input_tokens": 1500, "output_tokens": 300},
        )

    reads = run_ai_reading(artifact, control, fake_reader, run_id="run_x")
    assert reads.status == "done" and len(reads.readings) == 2
    assert (control / "renders" / "ES-100.png").exists()
    assert reads.input_tokens == 1500 and reads.run_id == "run_x"
    failed = next(r for r in reads.readings if r.frame_code == "ES-101")
    assert failed.read.uncertainties and "rate limited" in failed.read.uncertainties[0]
    assert any("ES-101" in n for n in reads.notes)
    assert load_ai_reads(control).status == "done"
    assert len(seen) == 2 and "planta" in seen[0]


def test_ai_specs_only_fill_what_the_rules_did_not_read():
    reads = AiReads(readings=read_frames([], lambda p, q: (SheetRead(), {})))
    reads.readings = [
        __import__("klave_engine.llm.reader", fromlist=["SheetReading"]).SheetReading(
            frame_code="ES-100",
            read=SheetRead(elements=[
                ElementRead(mark="K-1", family="castillo", section_cm="15x20", rebar="4#3",
                            confidence=0.9),
                ElementRead(mark="K-2", family="castillo", section_cm="20x25", confidence=0.8),
                ElementRead(mark="T-1", family="trabe", confidence=0.5),  # nothing to add
            ]),
        )
    ]
    specs = ai_element_specs(reads)
    assert [s["mark"] for s in specs] == ["K-1", "K-2"]
    assert specs[0]["source"] == "ia" and specs[0]["confidence"] == 0.54
    inventory = ScheduleInventory(by_mark={
        "K-1": ElementSpec(mark="K-1", family="castillo", section_cm=(15, 15), source="cuadro",
                           source_text="cuadro", confidence=0.95),
    })
    added = merge_external_specs(inventory, specs)
    assert added == 2
    assert inventory.by_mark["K-1"].section_cm == (15, 15)  # the cuadro keeps its section
    assert inventory.by_mark["K-1"].rebar == "4#3"  # the IA filled the missing armado
    assert inventory.by_mark["K-2"].section_cm == (20, 25)
    assert inventory.by_mark["K-2"].source == "ia"
