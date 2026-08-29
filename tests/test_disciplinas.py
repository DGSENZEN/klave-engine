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
