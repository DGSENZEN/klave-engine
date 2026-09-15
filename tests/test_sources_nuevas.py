"""Las fuentes oficiales nuevas se leen renglón por renglón de extractos
reales: SICT costo directo, CONAGUA, INIFECH (quince regiones) y la UEC de
Guanajuato (tabulador en Excel por región, materiales y maquinaria)."""

import json
from pathlib import Path

import pytest
from klave_engine.costing.sources.conagua import parse_conagua_lines
from klave_engine.costing.sources.guanajuato import (
    parse_guanajuato_maquinaria_table,
    parse_guanajuato_materiales_table,
    parse_guanajuato_sheet,
    parse_guanajuato_tabulador,
)
from klave_engine.costing.sources.inifech import parse_inifech_lines
from klave_engine.costing.sources.pdftext import money
from klave_engine.costing.sources.registry import SOURCES
from klave_engine.costing.sources.sict_costo_directo import parse_sict_costo_directo_lines

FIXTURES = Path(__file__).parent / "fixtures" / "sources"


def lines(name: str) -> list[str]:
    return (FIXTURES / name).read_text(encoding="utf-8").splitlines()


def test_money_cleans_published_spacing():
    assert money("$ 1 ,006.84") == 1006.84
    assert money("$  8 3.76") == 83.76
    assert money("35.39") == 35.39
    assert money("m³") is None


def test_sict_rows_close_on_their_price_line():
    rows = list(parse_sict_costo_directo_lines(lines("sict_costo_directo_p91.txt"), page=91))
    assert rows[0]["clave"] == "101.02.1150"
    assert rows[0]["unit"] == "m³" and rows[0]["price"] == 35.39
    assert rows[0]["description"].startswith("Despalme de 20 cm de espesor")
    assert rows[0]["description"].endswith("(N·CTR·CAR·1·01·002/11).")
    assert rows[0]["linea"] == 1034 and rows[0]["page"] == 91
    # El capítulo «1 CONSTRUCCIÓN» da contexto a los renglones que siguen.
    assert rows[0]["group_description"] == "CONSTRUCCIÓN"
    assert [r["price"] for r in rows[:5]] == [35.39, 38.66, 43.40, 50.27, 58.20]
    assert all(r["price"] for r in rows)


def test_conagua_rows_carry_their_group_and_clean_prices():
    rows = list(parse_conagua_lines(lines("conagua_p61.txt"), page=61))
    first = rows[0]
    assert first["clave"] == "8002-03" and first["unit"] == "M" and first["price"] == 254.66
    assert first["group_clave"] == "8002"
    assert first["group_description"].startswith("SUMINISTRO DE TUBERÍA DE ASBESTO-CEMENTO")
    assert first["description"] == '100 MM (4") DE DIÁMETRO.'
    assert next(r for r in rows if r["clave"] == "8002-06")["price"] == 1006.84
    later = list(parse_conagua_lines(lines("conagua_p31.txt"), page=31))
    assert later[0]["clave"] == "2282-06" and later[0]["price"] == 83.76
    assert later[0]["unit"] == "PZA"
    # Las líneas sin clave entre renglones son contexto del grupo.
    dos = next(r for r in later if r["clave"] == "2282-11")
    assert "INSTALACIÓN DE PIEZAS ESPECIALES" in dos["group_description"]


def test_inifech_rows_carry_fifteen_regions():
    rows = list(parse_inifech_lines(lines("inifech_p1.txt"), page=1))
    first = rows[0]
    assert first["clave"] == "1101000011" and first["unit"] == "M2"
    assert first["price"] == 14.11 and first["group_clave"] == "1101"
    assert first["description"].startswith("LIMPIEZA, TRAZO Y NIVELACION")
    assert len(first["extra"]["regiones"]) == 15
    regiones = first["extra"]["regiones"]
    assert regiones["15"] == 14.11 and regiones["11"] == 14.32
    # Código solo en su línea, descripción en cuatro líneas, precios al final.
    second = rows[1]
    assert second["clave"] == "1101000031" and second["unit"] == "M3"
    assert second["price"] == 115.30
    assert second["description"].endswith("P.U.O.T.")


def test_guanajuato_sheet_reads_hierarchy_and_prices():
    rows = json.loads((FIXTURES / "guanajuato_tabulador_RI_head.json").read_text(encoding="utf-8"))
    parsed = list(parse_guanajuato_sheet(rows, region="I"))
    assert parsed[0]["clave"] == "UEC.ED.10.100.1010"
    assert parsed[0]["unit"] == "m2" and parsed[0]["price"] == 66.54
    assert parsed[0]["group_clave"] == "100"
    assert parsed[0]["group_description"] == "PRELIMINARES · Despalmes"
    demolicion = next(r for r in parsed if r["clave"] == "UEC.ED.10.105.1015")
    assert demolicion["unit"] == "m3" and demolicion["price"] == 1330.7
    assert demolicion["group_description"] == "PRELIMINARES · Demoliciones manuales"


def test_guanajuato_regions_merge_into_one_source(tmp_path):
    from openpyxl import Workbook

    def workbook(name: str, price: float, extra_clave: str | None = None) -> None:
        wb = Workbook()
        ws = wb.active
        ws.append(["Código", "Concepto", "Unidad", "Cantidad", "Costo"])
        ws.append(["10", "PRELIMINARES", None, None, None])
        ws.append(["100", "Despalmes", None, None, None])
        ws.append(["UEC.ED.10.100.1010", "Despalme tipo A", "m2", 1, price])
        if extra_clave:
            ws.append([extra_clave, "Solo en esta región", "m2", 1, 5.0])
        wb.save(tmp_path / name)

    workbook("gto_RI.xlsx", 66.54)
    workbook("gto_RII.xlsx", 69.43, extra_clave="UEC.ED.10.100.1099")
    rows = list(parse_guanajuato_tabulador(tmp_path / "gto_RI.xlsx"))
    assert [r["clave"] for r in rows] == ["UEC.ED.10.100.1010", "UEC.ED.10.100.1099"]
    assert rows[0]["price"] == 66.54
    assert rows[0]["extra"]["regiones"] == {"I": 66.54, "II": 69.43}
    # La clave que solo existe en la región II entra con ese precio.
    assert rows[1]["price"] == 5.0 and rows[1]["extra"]["regiones"] == {"II": 5.0}


def test_guanajuato_material_and_machinery_tables():
    table = json.loads((FIXTURES / "guanajuato_materiales_tabla.json").read_text(encoding="utf-8"))
    rows = list(parse_guanajuato_materiales_table(table))
    arena = rows[0]
    assert arena["clave"] == "GTO-MAT-ARENA" and arena["unit"] == "m3"
    assert arena["price"] == 242.09
    assert arena["extra"]["regiones"] == {
        "1": 242.09, "2": 252.61, "3": 320.0, "4": 260.0, "5": 225.0,
    }
    assert arena["extra"]["presentacion"] == "Camión de 7 m3"
    tezontle = next(r for r in rows if r["description"] == "Tezontle")
    assert tezontle["extra"]["regiones"] == {"6": 82.76} and tezontle["price"] == 82.76
    cemento = next(r for r in rows if r["description"].startswith("Cemento"))
    assert cemento["unit"] == "Ton" and cemento["price"] == 4148.08
    table = json.loads((FIXTURES / "guanajuato_maquinaria_tabla.json").read_text(encoding="utf-8"))
    machines = list(parse_guanajuato_maquinaria_table(table))
    assert machines[0]["description"] == "Vibrador de inmersión"
    assert machines[0]["unit"] == "HORA" and machines[0]["price"] == 120.0
    assert machines[0]["extra"]["motor"] == "Gasolina"
    assert machines[0]["extra"]["potencia_hp"] == "5.5"


@pytest.mark.parametrize("key", [
    "sict-costo-directo-2026", "conagua-2026", "inifech-chiapas", "guanajuato-uec-2026",
    "guanajuato-materiales-2026-09", "guanajuato-maquinaria-2026-09",
])
def test_every_new_source_is_registered_with_its_file(key):
    spec = SOURCES[key]
    assert spec.url.startswith("https://") and spec.filename and spec.vigencia
    assert spec.kind in ("precios_unitarios", "costo_horario", "insumos")
