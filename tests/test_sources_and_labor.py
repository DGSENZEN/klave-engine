"""Reference sources, salario real, and costo horario — the law, in code."""
# ruff: noqa: E501  (verbatim PDF layout samples)

from pathlib import Path

import pytest
from klave_engine.costing.equipment import EquipmentParameters, compute_costo_horario
from klave_engine.costing.labor import SALARIO_MINIMO_GENERAL, FsrParameters, compute_fsr
from klave_engine.costing.sources.cdmx_tabulador import parse_cdmx_lines
from klave_engine.costing.sources.sict_maquinaria import parse_sict_lines

CDMX_SAMPLE = """
        Clave                   Concepto de Obra              Unidad     P. U.
      GC17E     Muros de tabique rojo recocido, con una cara aparente, asentados con
                mortero cemento-arena en proporción 1:5.
      GC17EA    Muro de tabique rojo recocido de 7 cm de espesor, una cara aparente. m2 430.66
      GC17FA    Muro de tabique rojo recocido de 7 cm de espesor, dos caras m2 453.12
                aparentes.
      AC22BB    Proyecto de la zona transparente de puente hiperestático, primeros 100 m2 880.23
                m2
      GC18      Muretes de tabique rojo, aplanado interior y exterior.
      GC18CB    Murete de tabique rojo de 11.5 cm de espesor, para base de domo de pieza 1,987.37
                0.60 x 0.60 x 0.60 m, aplanado en interior.
"""

SICT_SAMPLE = """
         Imagen  Serie Descripción de la maquinaría o equipo VA USD VA MXN Activo Espera Reserva
                 1010 MOTOSIERRAS
                 1011 Motosierra marca STIHL, modelo MS 382 de 28" de $771.70 $14,893.80 $100.81 $83.85 $3.22
                    corte con motor a gasolina de 5.2 HP, cilindrada de
                    72.2, paso de cadena de 3/8"
                 1326 Excavadora sobre orugas marca KOMATSU modelo $403,000.00 $7,777,900.00 $1,658.14 $1,049.00 $949.66
                    PC390LC-8M0, motor a Diesel de 260 HP.
"""


def test_cdmx_rows_wrap_and_inherit_their_group():
    rows = list(parse_cdmx_lines(CDMX_SAMPLE.splitlines(), page=61))
    by_clave = {r["clave"]: r for r in rows}
    assert set(by_clave) == {"GC17EA", "GC17FA", "AC22BB", "GC18CB"}
    assert by_clave["GC17EA"]["price"] == 430.66 and by_clave["GC17EA"]["unit"] == "m2"
    assert by_clave["GC17FA"]["description"].endswith("dos caras aparentes.")
    assert by_clave["GC17EA"]["group_clave"] == "GC17E"
    assert "una cara aparente" in by_clave["GC17EA"]["group_description"]
    assert by_clave["GC17FA"]["group_clave"] == ""  # its parent GC17F is not in the sample
    assert by_clave["AC22BB"]["price"] == 880.23  # the wrapped unit token is dropped
    assert by_clave["GC18CB"]["unit"] == "pieza" and by_clave["GC18CB"]["price"] == 1987.37
    assert by_clave["GC18CB"]["group_clave"] == "GC18"


def test_sict_rows_carry_all_three_hourly_costs():
    rows = list(parse_sict_lines(SICT_SAMPLE.splitlines(), page=12))
    assert [r["clave"] for r in rows] == ["1011", "1326"]
    saw = rows[0]
    assert saw["group_description"] == "MOTOSIERRAS" and saw["unit"] == "hr"
    assert saw["price"] == 100.81 and saw["extra"]["espera"] == 83.85
    assert saw["description"].endswith('paso de cadena de 3/8"')
    assert rows[1]["extra"]["va_mxn"] == 7_777_900.00


@pytest.mark.skipif(
    not Path("data/sources/cdmx_tabulador_actualizacion_2026_junio.pdf").exists(),
    reason="official CDMX PDF not downloaded locally",
)
def test_real_cdmx_tabulador_parses_thousands_of_priced_rows():
    from klave_engine.costing.sources.cdmx_tabulador import parse_cdmx_tabulador

    rows = list(parse_cdmx_tabulador(Path("data/sources/cdmx_tabulador_actualizacion_2026_junio.pdf")))
    assert len(rows) > 5000
    assert sum(1 for r in rows if r["price"] > 0) / len(rows) > 0.99
    assert sum(1 for r in rows if r.get("unit_guess")) / len(rows) < 0.01


def test_fsr_for_a_peon_at_minimum_wage_is_in_the_known_range():
    result = compute_fsr(SALARIO_MINIMO_GENERAL, FsrParameters())
    assert result.tp == 383.0 and result.tl == 291.0
    assert result.factor_integracion == pytest.approx(1.0493, abs=1e-4)
    assert result.employer_daily["eym_excedente"] == 0.0  # below 3 UMA
    assert result.employer_daily["cesantia_vejez"] == pytest.approx(
        result.salario_base_cotizacion * 0.06026, abs=0.01
    )
    assert 1.60 <= result.fsr <= 1.85
    assert result.salario_real == pytest.approx(SALARIO_MINIMO_GENERAL * result.fsr, abs=0.01)
    assert any("art. 191" in note for note in result.notes)


def test_fsr_rises_with_salary_band_and_isn_toggle():
    low = compute_fsr(315.04)
    high = compute_fsr(900.0)
    assert high.employer_daily["eym_excedente"] > 0
    assert high.employer_daily["cesantia_vejez"] / high.salario_base_cotizacion > (
        low.employer_daily["cesantia_vejez"] / low.salario_base_cotizacion
    )
    with_isn = compute_fsr(315.04, FsrParameters(isn_in_fsr=True))
    assert with_isn.fsr > low.fsr and "isn" in with_isn.employer_daily


def test_costo_horario_follows_the_reglamento_line_by_line():
    params = EquipmentParameters(
        vm=1_000_000, vr=100_000, ve=10_000, hea=2000, i=0.12, s=0.03, ko=0.8,
        gh=12.0, pc=25.0, ah=0.05, ga=0.02, pa=90.0, pn=60_000, vn=3000,
        pa_e=0, va=0, sr=1200.0, ht=8,
    )
    result = compute_costo_horario(params)
    assert result.depreciacion == 90.0
    assert result.inversion == pytest.approx(275.0 * 0.12)
    assert result.seguros == pytest.approx(275.0 * 0.03)
    assert result.mantenimiento == 72.0
    assert result.combustible == 300.0 and result.lubricantes == pytest.approx(6.3)
    assert result.llantas == 20.0 and result.piezas_especiales == 0.0
    assert result.operacion == 150.0
    assert result.costo_horario == pytest.approx(
        result.cargos_fijos + result.consumos + result.operacion, abs=0.01
    )
