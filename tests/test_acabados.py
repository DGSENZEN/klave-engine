"""La marca de acabado sabe su clave: PI y PL declaran el piso y el plafón
del local donde están parados."""

import ezdxf
from klave_engine.common.ids import IdGenerator
from klave_engine.detection.acabado_marks import detect_acabado_marks
from klave_engine.dxf.parser import DxfParser


def test_la_marca_sabe_su_clave(tmp_path):
    doc = ezdxf.new("R2010")
    pi = doc.blocks.new(name="PI")
    pi.add_circle((0, 0), 0.15)
    pi.add_attdef("P1", (0, 0), dxfattribs={"height": 0.1})
    pl = doc.blocks.new(name="PL")
    pl.add_circle((0, 0), 0.15)
    pl.add_attdef("PL1", (0, 0), dxfattribs={"height": 0.1})
    msp = doc.modelspace()
    msp.add_blockref("PI", (2, 2)).add_auto_attribs({"P1": "4"})
    msp.add_blockref("PL", (3, 3)).add_auto_attribs({"PL1": "A"})
    msp.add_blockref("PI", (9, 9))  # sin clave
    path = tmp_path / "aca.dxf"
    doc.saveas(path)

    entities = DxfParser().parse_file(path).entities
    out = detect_acabado_marks(entities, IdGenerator("d"))
    assert len(out.detections) == 2
    por_familia = {d.properties["fixture_family"]: d for d in out.detections}
    assert por_familia["acabado_piso"].properties["clave"] == "4"
    assert por_familia["acabado_plafon"].properties["clave"] == "A"
    assert any("marcas de acabado sin clave" in w for w in out.warnings)


def test_el_local_sabe_su_piso_y_su_plafon(tmp_path):
    from klave_engine.detection.disciplines import route_sheet
    from klave_engine.detection.suite import DetectorSuiteConfig, run_detectors
    from klave_engine.geometry.spatial_index import SpatialIndex
    from klave_engine.ingestion.manifest import ProjectManifest

    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()

    def muro(a, b, t=0.15):
        (x0, y0), (x1, y1) = a, b
        if y0 == y1:
            msp.add_line((x0, y0 - t/2), (x1, y1 - t/2), dxfattribs={"layer": "A-MUROS"})
            msp.add_line((x0, y0 + t/2), (x1, y1 + t/2), dxfattribs={"layer": "A-MUROS"})
        else:
            msp.add_line((x0 - t/2, y0), (x1 - t/2, y1), dxfattribs={"layer": "A-MUROS"})
            msp.add_line((x0 + t/2, y0), (x1 + t/2, y1), dxfattribs={"layer": "A-MUROS"})

    for a, b in [((0, 0), (7, 0)), ((0, 4), (7, 4)), ((0, 0), (0, 4)),
                 ((4, 0), (4, 4)), ((7, 0), (7, 4))]:
        muro(a, b)
    msp.add_text("SALA", height=0.2).set_placement((1.5, 2))
    msp.add_text("BAÑO", height=0.2).set_placement((5, 2))
    pi = doc.blocks.new(name="PI")
    pi.add_circle((0, 0), 0.15)
    pi.add_attdef("P1", (0, 0), dxfattribs={"height": 0.1})
    pl = doc.blocks.new(name="PL")
    pl.add_circle((0, 0), 0.15)
    pl.add_attdef("PL1", (0, 0), dxfattribs={"height": 0.1})
    msp.add_blockref("PI", (2, 1)).add_auto_attribs({"P1": "4"})
    msp.add_blockref("PL", (2, 3)).add_auto_attribs({"PL1": "A"})
    msp.add_blockref("PI", (5.5, 2)).add_auto_attribs({"P1": "7"})
    path = tmp_path / "10-10_acabados.dxf"
    doc.saveas(path)
    entities = DxfParser().parse_file(path).entities

    suite = route_sheet("10-10_acabados.dxf")
    assert suite.key == "acabados" and suite.detect is not None

    manifest = ProjectManifest(project_id="t", project_name="t", root_path=str(tmp_path))
    outputs = run_detectors(
        entities, SpatialIndex(entities), manifest, DetectorSuiteConfig(),
        ids=IdGenerator("d"), units=None, structural=False, suite=suite,
    )
    rooms = [d for o in outputs for d in o.detections if d.detection_type.value == "room"]
    assert len(rooms) >= 2
    por_clave = {(d.properties.get("piso_clave"), d.properties.get("plafon_clave"))
                 for d in rooms}
    assert ("4", "A") in por_clave  # la sala: piso 4, plafón A
    assert any(p == "7" for p, _ in por_clave)  # el baño: piso 7


def test_el_pipeline_agrega_las_areas_por_clave(data_dir, tmp_path):
    import json as jsonlib

    from klave_engine.common.config import get_settings
    from klave_engine.costing.hallazgos import _classify
    from klave_engine.pipeline import run_full_pipeline

    # La regla del diagnóstico clasifica el aviso agrupado.
    rule = _classify("2 locales sin clave de acabado: su área no pertenece a "
                     "ningún acabado declarado.")
    assert rule.group == "locales_sin_acabado" and rule.severity == "revisar"

    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()

    def muro(a, b, t=0.15):
        (x0, y0), (x1, y1) = a, b
        if y0 == y1:
            msp.add_line((x0, y0 - t/2), (x1, y1 - t/2), dxfattribs={"layer": "A-MUROS"})
            msp.add_line((x0, y0 + t/2), (x1, y1 + t/2), dxfattribs={"layer": "A-MUROS"})
        else:
            msp.add_line((x0 - t/2, y0), (x1 - t/2, y1), dxfattribs={"layer": "A-MUROS"})
            msp.add_line((x0 + t/2, y0), (x1 + t/2, y1), dxfattribs={"layer": "A-MUROS"})

    for a, b in [((0, 0), (7, 0)), ((0, 4), (7, 4)), ((0, 0), (0, 4)),
                 ((4, 0), (4, 4)), ((7, 0), (7, 4))]:
        muro(a, b)
    msp.add_text("SALA", height=0.2).set_placement((1.5, 2))
    msp.add_text("BAÑO", height=0.2).set_placement((5, 2))
    pi = doc.blocks.new(name="PI")
    pi.add_circle((0, 0), 0.15)
    pi.add_attdef("P1", (0, 0), dxfattribs={"height": 0.1})
    msp.add_blockref("PI", (2, 1)).add_auto_attribs({"P1": "4"})

    root = data_dir / "uploads" / "acabados_demo"
    (root / "drawings").mkdir(parents=True)
    doc.saveas(root / "drawings" / "10-10_acabados.dxf")
    settings = get_settings()
    run_full_pipeline(root, settings)

    artifact = root / settings.processed_dir_name / "acabados.json"
    assert artifact.exists()
    rows = jsonlib.loads(artifact.read_text())
    piso4 = next(r for r in rows if r["tipo"] == "piso" and r["clave"] == "4")
    assert piso4["locales"] == 1 and piso4["area_m2"] and piso4["area_m2"] > 5
