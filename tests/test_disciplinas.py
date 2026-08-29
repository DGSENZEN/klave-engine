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
