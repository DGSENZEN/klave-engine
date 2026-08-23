"""Layer hints match tokens, never raw substrings: a mobiliario layer is not
a concrete wall because its name starts with MC."""

from klave_engine.detection.results import layer_matches
from klave_engine.detection.wall_detector import WallDetectorConfig


def test_short_hints_need_the_whole_token():
    concrete = WallDetectorConfig().concrete_layer_hints
    assert layer_matches("E-MC-01", concrete)
    assert layer_matches("MUROS_CONCRETO", concrete)
    assert layer_matches("A-MURO CONC", concrete)
    assert not layer_matches("A-MCOBILIARIO", concrete)
    assert not layer_matches("EMCAJETIN", concrete)


def test_long_hints_may_start_a_token():
    walls = WallDetectorConfig().layer_hints
    assert layer_matches("A-MUROS", walls)
    assert layer_matches("MURO-15", walls)
    assert layer_matches("TABIQUES", walls)
    assert not layer_matches("A-ARMADO", walls)


def test_avoid_hints_catch_plurals_and_long_forms():
    avoid = WallDetectorConfig().avoid_layer_hints
    assert layer_matches("A-EJES", avoid)
    assert layer_matches("DIMENSIONES", avoid)
    assert layer_matches("S-DIM", avoid)
    assert not layer_matches("A-DIMA-PISO", avoid)  # DIMA is not DIM
