"""Qué hoja corre detectores estructurales: el nombre decide, y los nombres
llegan slugificados (la ñ se pierde en la subida)."""

from klave_engine.detection.inventory import guess_discipline, reads_as_structure


def test_albanileria_y_el_indice_no_son_estructura():
    # «albañilería» es "alba_iler_a" en disco. Ambas grafías cuentan.
    assert guess_discipline("03-03_alba_iler_a_-_26_01_15.dwg") == "albanileria"
    assert guess_discipline("03 ALBAÑILERÍA.dwg") == "albanileria"
    assert guess_discipline("01-00_indice_l_04.dwg") == "indice"
    assert reads_as_structure("03-03_alba_iler_a_-_26_01_15.dwg") is False
    assert reads_as_structure("01-00_indice_l_04.dwg") is False
    # Lo que ya funcionaba no se mueve: estructura sigue siendo estructura y
    # un nombre desconocido sigue contando como estructura.
    assert reads_as_structure("02-02_estructural_l_04_-_26_01_15.dwg") is True
    assert reads_as_structure("Plano 1.dwg") is True


def test_el_registro_reproduce_el_ruteo_de_hoy():
    from klave_engine.detection.disciplines import REGISTRY, route_sheet

    # La tabla de la casa: nombre → disciplina → ¿detectores estructurales?
    tabla = [
        ("02-02_estructural_l_04.dwg", "estructural", True),
        ("Plano 1.dwg", "estructural", True),          # desconocido = estructura
        ("02-05_sanitario_l_04.dwg", "sanitaria", False),
        ("03-09_gas_l_04.dwg", "gas", False),
        ("03-03_alba_iler_a.dwg", "albanileria", False),
        ("01-00_indice_l_04.dwg", "indice", False),
        ("04-08_aa_l_04.dwg", "aire", False),
    ]
    for nombre, key, estructural in tabla:
        suite = route_sheet(nombre)
        assert suite.key == key, nombre
        assert suite.structural is estructural, nombre
    assert "estructural" in REGISTRY and REGISTRY["estructural"].structural


def test_el_contenido_vota_su_disciplina(tmp_path):
    import ezdxf
    from klave_engine.detection.disciplines import vote_content
    from klave_engine.dxf.parser import DxfParser

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for i in range(30):
        msp.add_line((i, 0), (i, 5), dxfattribs={"layer": "00-SANITARIA"})
    path = tmp_path / "voto.dxf"
    doc.saveas(path)
    entities = DxfParser().parse_file(path).entities
    assert vote_content(entities) == ("sanitaria", 30)

    # Contenido mixto sin ganador claro: nadie vota.
    doc2 = ezdxf.new("R2010")
    msp2 = doc2.modelspace()
    for i in range(10):
        msp2.add_line((i, 0), (i, 5), dxfattribs={"layer": "00-SANITARIA"})
    for i in range(9):
        msp2.add_line((i, 10), (i, 15), dxfattribs={"layer": "GAS"})
    path2 = tmp_path / "mixto.dxf"
    doc2.saveas(path2)
    entities2 = DxfParser().parse_file(path2).entities
    assert vote_content(entities2) is None


def test_hidrosanitaria_ocupa_el_hueco_detect(tmp_path):
    """El primer inquilino real del registro: la hoja sanitaria se lee por su
    suite, y produce exactamente lo que producía el trío por default."""
    import ezdxf
    from klave_engine.common.ids import IdGenerator
    from klave_engine.detection.disciplines import route_sheet
    from klave_engine.detection.suite import DetectorSuiteConfig, run_detectors
    from klave_engine.dxf.parser import DxfParser
    from klave_engine.geometry.spatial_index import SpatialIndex
    from klave_engine.ingestion.manifest import ProjectManifest

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    block = doc.blocks.new(name="DESCSAN1")
    block.add_line((0, 0), (0.3, 0))
    msp.add_blockref("DESCSAN1", (5, 5))
    msp.add_lwpolyline([(0, 0), (12, 0)], dxfattribs={"layer": "00-SANITARIA"})
    path = tmp_path / "02-05_sanitario.dxf"
    doc.saveas(path)
    entities = DxfParser().parse_file(path).entities

    suite = route_sheet("02-05_sanitario.dxf")
    assert suite.key == "sanitaria" and suite.detect is not None

    manifest = ProjectManifest(project_id="t", project_name="t", root_path=str(tmp_path))
    config = DetectorSuiteConfig()
    outputs = run_detectors(
        entities, SpatialIndex(entities), manifest, config,
        ids=IdGenerator("d"), units=None, structural=False, suite=suite,
    )
    tipos = sorted(d.detection_type.value for o in outputs for d in o.detections)
    # El trío de siempre: el mueble se detecta; la corrida no (sin unidades).
    assert "fixture" in tipos


def test_canceleria_detecta_la_pieza_sin_recontarla(tmp_path):
    """La suite de cancelería: el globo con clave es UNA pieza — el detector
    genérico de vanos no la vuelve a contar."""
    import ezdxf
    from klave_engine.common.ids import IdGenerator
    from klave_engine.detection.disciplines import route_sheet
    from klave_engine.detection.suite import DetectorSuiteConfig, run_detectors
    from klave_engine.dxf.parser import DxfParser
    from klave_engine.geometry.spatial_index import SpatialIndex
    from klave_engine.ingestion.manifest import ProjectManifest

    doc = ezdxf.new("R2010")
    block = doc.blocks.new(name="CANC_ALUM")
    block.add_line((0, 0), (0.4, 0))
    block.add_attdef("CLAVE", (0, 0), dxfattribs={"height": 0.2})
    ref = doc.modelspace().add_blockref(
        "CANC_ALUM", (5, 5), dxfattribs={"layer": "CANCELERIA"}
    )
    ref.add_auto_attribs({"CLAVE": "CA-07"})
    path = tmp_path / "12-12_canceleria.dxf"
    doc.saveas(path)
    entities = DxfParser().parse_file(path).entities

    suite = route_sheet("12-12_canceleria.dxf")
    assert suite.key == "canceleria" and suite.detect is not None

    manifest = ProjectManifest(project_id="t", project_name="t", root_path=str(tmp_path))
    outputs = run_detectors(
        entities, SpatialIndex(entities), manifest, DetectorSuiteConfig(),
        ids=IdGenerator("d"), units=None, structural=False, suite=suite,
    )
    openings = [d for o in outputs for d in o.detections
                if d.detection_type.value == "opening"]
    assert len(openings) == 1
    assert openings[0].label == "CA-07"
    assert openings[0].properties["opening_family"] == "cancel"


def test_el_fondo_arquitectonico_es_sustrato():
    from klave_engine.detection.disciplines import route_sheet

    assert route_sheet("00 XREF L.04 - 26.01.15.dwg").key == "arquitectura"
    assert route_sheet("01 ARQ L.04 - 26.01.15.dwg").key == "arquitectura"
    assert route_sheet("00_xref_l_04_-_26_01_15.dwg").key == "arquitectura"
    suite = route_sheet("00 XREF L.04.dwg")
    assert suite.structural is False and suite.detect is not None


def test_el_sustrato_se_ve_pero_no_cobra():
    from klave_engine.costing.apu import build_all_apus
    from klave_engine.costing.boq import generate_bill_of_quantities
    from klave_engine.costing.catalog import build_default_catalog
    from klave_engine.costing.models import CostingAssumptions
    from klave_engine.detection.results import DetectionType, make_detection
    from klave_engine.dxf.units import DrawingUnits

    from tests.precios import LIBRO

    def muro(det_id, substrate):
        props = {"estimated_length": 10.0, "wall_kind": None}
        if substrate:
            props["substrate"] = True
        return make_detection(
            det_id, DetectionType.wall, f"M-{det_id}", (0, 0, 10, 0.15), 0.8, [],
            "wall_pair", [], props,
        )

    dets = [muro("real", False), muro("fondo", True)]
    assumptions = CostingAssumptions()
    catalog = [c for c in build_default_catalog(assumptions) if c.code == "EST-004"]
    units = DrawingUnits(unit="m", source="declared", confidence=1.0)
    boq = generate_bill_of_quantities(
        "t", dets, units, catalog, build_all_apus(catalog, LIBRO), assumptions=assumptions
    )
    linea = next(li for li in boq.lines if li.concept_code == "EST-004")
    # Solo el muro real cobra: 10 m × altura, no 20.
    assert linea.raw_quantity == 10.0
    assert "fondo" not in linea.source_detections
