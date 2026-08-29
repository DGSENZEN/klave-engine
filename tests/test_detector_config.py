"""Un config externo ajusta umbrales; no apaga el escalado por unidades."""

from klave_engine.common.io import write_json
from klave_engine.detection.suite import DetectorSuiteConfig, load_detector_config
from klave_engine.dxf.units import DrawingUnits


def test_config_externo_overlaya_el_preset_escalado(tmp_path):
    path = tmp_path / "detectors.json"
    write_json(path, {"wall": {"min_length": 9.99}})
    units = DrawingUnits(unit="m", source="dxf_header", confidence=0.9)
    preset = DetectorSuiteConfig.preset_for_units(units, None)
    loaded = load_detector_config(path, units, None)
    # El campo del archivo manda…
    assert loaded.wall.min_length == 9.99
    # …y todo lo demás conserva el preset escalado, no el default crudo.
    assert loaded.slab.min_area == preset.slab.min_area
    assert loaded.grid.min_relative_length == preset.grid.min_relative_length
