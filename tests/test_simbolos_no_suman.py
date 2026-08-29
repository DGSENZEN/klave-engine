"""El linework interno de un bloque que la tabla reconoce como mueble ya se
contó como pieza: no debe sumar metros de corrida ni parearse como muro."""

import ezdxf
from klave_engine.detection.instalaciones_symbols import es_trazo_de_simbolo
from klave_engine.detection.inventory import build_inventory
from klave_engine.detection.wall_detector import WallDetectorConfig, detect_walls
from klave_engine.dxf.parser import DxfParser
from klave_engine.geometry.spatial_index import SpatialIndex


def _parse(tmp_path, build):
    doc = ezdxf.new("R2010")
    build(doc)
    path = tmp_path / "plano.dxf"
    doc.saveas(path)
    return DxfParser().parse_file(path)


def test_trazo_de_inodoro_no_suma_corrida(tmp_path):
    def build(doc):
        block = doc.blocks.new(name="INODORO")
        # El bloque dibuja 2 m de línea sobre la capa del sistema.
        block.add_line((0, 0), (2, 0), dxfattribs={"layer": "00-SANITARIA"})
        msp = doc.modelspace()
        msp.add_blockref("INODORO", (10, 10), dxfattribs={"layer": "MUEBLES"})
        # La corrida real de la hoja: 5 m directos.
        msp.add_lwpolyline([(0, 0), (5, 0)], dxfattribs={"layer": "00-SANITARIA"})

    drawing = _parse(tmp_path, build)
    child = next(e for e in drawing.entities
                 if (e.properties or {}).get("parent_insert"))
    assert es_trazo_de_simbolo(child) is True
    inventory = build_inventory(drawing.entities, None, [])
    runs = {r.layer: r for s in inventory.sheets for r in s.runs}
    assert abs(runs["00-SANITARIA"].length_du - 5.0) < 1e-6


def test_trazo_de_inodoro_no_parea_como_muro(tmp_path):
    def build(doc):
        block = doc.blocks.new(name="INODORO")
        block.add_line((0, 0), (3, 0), dxfattribs={"layer": "MURO"})
        block.add_line((0, 0.15), (3, 0.15), dxfattribs={"layer": "MURO"})
        msp = doc.modelspace()
        msp.add_blockref("INODORO", (20, 20))
        # Un muro real, directo.
        msp.add_line((0, 0), (4, 0), dxfattribs={"layer": "MURO"})
        msp.add_line((0, 0.15), (4, 0.15), dxfattribs={"layer": "MURO"})

    drawing = _parse(tmp_path, build)
    config = WallDetectorConfig(min_length=1.0, min_thickness=0.05, max_thickness=0.5)
    output = detect_walls(drawing.entities, SpatialIndex(drawing.entities), config)
    walls = [d for d in output.detections if d.detection_type.value == "wall"]
    assert len(walls) == 1
