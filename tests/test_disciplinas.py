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
