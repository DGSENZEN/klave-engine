"""El índice de prefabricados: cada definición se clasifica una vez y
estampa sus instancias — el primitivo central del motor multidisciplina."""

import ezdxf
from klave_engine.detection.prefabs import build_prefab_index
from klave_engine.dxf.parser import DxfParser


def test_definicion_clasificada_una_vez_con_sus_instancias(tmp_path):
    doc = ezdxf.new("R2010")
    inodoro = doc.blocks.new(name="INODORO")
    inodoro.add_line((0, 0), (0.6, 0))
    contenedor = doc.blocks.new(name="BANO-TIPO")
    contenedor.add_blockref("INODORO", (2, 2))
    msp = doc.modelspace()
    msp.add_blockref("INODORO", (10, 10))
    msp.add_blockref("INODORO", (20, 10))
    msp.add_blockref("BANO-TIPO", (30, 30))
    path = tmp_path / "prefabs.dxf"
    doc.saveas(path)

    drawing = DxfParser().parse_file(path)
    index = {p.name: p for p in build_prefab_index(drawing.entities, drawing.block_attdefs)}

    # INODORO: dos colocaciones directas + una anidada en BANO-TIPO.
    assert index["INODORO"].familia == "wc"
    assert len(index["INODORO"].instances) == 3
    assert index["BANO-TIPO"].familia is None  # contenedor: la tabla no lo reconoce
    assert len(index["BANO-TIPO"].instances) == 1
    # Los bloques anónimos (*X…) jamás entran al índice.
    assert not any(name.startswith("*") for name in index)


def test_attdefs_y_anotacion(tmp_path):
    doc = ezdxf.new("R2010")
    bubble = doc.blocks.new(name="NOMENCLATURA-V")
    bubble.add_attdef("CLAVE", (0, 0), dxfattribs={"height": 0.2})
    cajetin = doc.blocks.new(name="PIE DE PLANO A1")
    cajetin.add_line((0, 0), (1, 0))
    msp = doc.modelspace()
    msp.add_blockref("NOMENCLATURA-V", (0, 0))
    msp.add_blockref("PIE DE PLANO A1", (50, 0))
    path = tmp_path / "attdefs.dxf"
    doc.saveas(path)

    drawing = DxfParser().parse_file(path)
    index = {p.name: p for p in build_prefab_index(drawing.entities, drawing.block_attdefs)}
    assert index["NOMENCLATURA-V"].attdefs == ["CLAVE"]
    assert index["PIE DE PLANO A1"].es_anotacion is True


def test_el_pipeline_escribe_el_indice_y_la_lectura_lo_sirve(data_dir, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from klave_engine.common import config as config_module
    from klave_engine.common.config import get_settings
    from klave_engine.evals.fixtures import write_demo_project
    from klave_engine.pipeline import run_full_pipeline

    from apps.api.main import create_app

    monkeypatch.setenv("KLAVE_USERS_DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    config_module.get_settings.cache_clear()
    settings = get_settings()
    root = data_dir / "uploads" / "demo_prefabs"
    write_demo_project(root)
    result = run_full_pipeline(root, settings)
    assert (root / settings.processed_dir_name / "prefab_index.json").exists()

    import json

    registry_path = data_dir / "projects_registry.json"
    registry = json.loads(registry_path.read_text()) if registry_path.exists() else {}
    registry[result.manifest.project_id] = str(root)
    registry_path.write_text(json.dumps(registry))

    client = TestClient(create_app())
    payload = client.get(f"/projects/{result.manifest.project_id}/lectura")
    assert payload.status_code == 200, payload.text
    assert isinstance(payload.json().get("prefabs"), list)
