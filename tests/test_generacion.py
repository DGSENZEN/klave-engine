"""Las plantillas de matriz por familia: un concepto sin matriz recibe una
generada desde la ficha de su texto, cada línea con su fuente, y la
calculadora de fórmulas no ejecuta nada que no sea aritmética."""

import pytest
from klave_engine.costing.generacion import (
    cargar_plantillas,
    elegir_plantilla,
    evaluar,
    ficha_numerica,
    generar,
)


def test_every_plantilla_line_and_rendimiento_carries_a_source():
    plantillas = cargar_plantillas()
    assert len(plantillas) >= 12
    for plantilla in plantillas:
        assert plantilla.rendimiento.source, plantilla.key
        for line in plantilla.lines:
            assert line.source, f"{plantilla.key} · {line.resource}"
        for name, var in plantilla.vars.items():
            assert var.source, f"{plantilla.key} · {name}"


def test_ficha_reads_fc_section_thickness_and_element():
    ficha = ficha_numerica("Columnas de concreto armado f'c=250 kg/cm² de 30x40 cm")
    assert ficha["fc"] == 250 and ficha["b_cm"] == 30 and ficha["h_cm"] == 40
    assert ficha["elemento"] == "columnas"
    ficha = ficha_numerica("Firme de concreto f'c=150 kg/cm² de 10 cm de espesor, acabado pulido")
    assert ficha["espesor_cm"] == 10 and ficha["fc"] == 150
    # La firma del plano manda sobre el texto.
    ficha = ficha_numerica("Columnas de concreto f'c=250", {"fc": 300, "section_cm": [40, 60]})
    assert ficha["fc"] == 300 and (ficha["b_cm"], ficha["h_cm"]) == (40, 60)


@pytest.mark.parametrize(
    ("description", "unit", "key"),
    [
        ("Columnas y castillos de concreto armado f'c=250 kg/cm²", "M3", "concreto-armado-m3"),
        ("Concreto f'c=250 kg/cm² en columnas, premezclado", "M3", "concreto-simple-m3"),
        ("Concreto hecho en obra f'c=150 kg/cm² en firmes", "M3", "concreto-en-obra-m3"),
        ("Cimbra común en trabes, acabado no aparente", "M2", "cimbra-m2"),
        ("Acero de refuerzo fy=4200 kg/cm² del n.º 3 al 8", "TON", "acero-refuerzo-ton"),
        ("Muro de block de concreto 15x20x40 asentado con mortero", "M2", "mamposteria-m2"),
        ("Aplanado de mezcla cemento-arena 1:4 en muros, acabado fino", "M2", "aplanado-m2"),
        ("Pintura vinílica en muros a dos manos", "M2", "pintura-m2"),
        ("Plafón de yeso en losa, acabado fino", "M2", "plafon-yeso-m2"),
        ("Piso de loseta cerámica 60×60 cm asentado con adhesivo", "M2", "piso-loseta-m2"),
        ("Firme de concreto f'c=150 kg/cm² de 10 cm, acabado pulido", "M2", "firme-m2"),
        ("Excavación estructural para cimentación por medios mecánicos", "M3", "excavacion-m3"),
        ("Relleno compactado con tepetate en capas de 20 cm", "M3", "relleno-m3"),
        ("Plantilla de concreto f'c=100 kg/cm², 5 cm", "M2", "plantilla-m2"),
        ("Cadena o dala de concreto armado 15x20 cm", "M", "dala-castillo-m"),
        ("Tubería de PVC sanitario de 100 mm", "M", "tuberia-m"),
    ],
)
def test_each_family_picks_its_plantilla(description, unit, key):
    plantilla = elegir_plantilla(description, unit)
    assert plantilla is not None and plantilla.key == key


def test_unknown_description_gets_no_plantilla():
    assert elegir_plantilla("Suministro de luminaria LED 18 W", "PZA") is None
    assert elegir_plantilla("Columnas de concreto armado", "PZA") is None  # unidad ajena


def test_columnas_formwork_comes_from_the_section():
    generada = generar("Columnas de concreto armado f'c=250 kg/cm² de 30x40 cm", "M3")
    assert generada.plantilla_key == "concreto-armado-m3"
    lines = {line.resource_code: line for line in generada.lines}
    # 2(b+h)/(b·h) con b y h en metros: 2 × 0.70 / 0.12 = 11.67 m² por m³.
    assert lines["MAT-CIMBRA"].quantity == pytest.approx(11.67, abs=0.01)
    assert lines["MAT-CONC250"].quantity == pytest.approx(1.03)
    assert lines["MAT-VARILLA"].quantity == pytest.approx(160 * 1.03)
    assert "CUAD-ALB-1x1" in lines and lines["CUAD-ALB-1x1"].quantity == pytest.approx(1 / 3)
    assert lines["EQ-HERRAMIENTA"].quantity == 1.0
    assert all(line.source for line in generada.lines)
    assert generada.rendimiento == pytest.approx(3.0)
    assert {c.code for c in generada.cuadrillas} >= {"CUAD-ALB-1x1", "CUAD-FIE-1x1"}
    assert generada.cuadrillas[0].members


def test_columnas_without_section_use_the_element_default():
    generada = generar("Columnas de concreto armado f'c=250 kg/cm²", "M3")
    lines = {line.resource_code: line for line in generada.lines}
    assert lines["MAT-CIMBRA"].quantity == pytest.approx(9.0)
    trabes = generar("Trabes de concreto armado f'c=250 kg/cm²", "M3")
    assert {line.resource_code: line for line in trabes.lines}["MAT-VARILLA"].quantity == (
        pytest.approx(120 * 1.03)
    )


def test_concrete_made_on_site_takes_cement_by_class_and_the_right_resource():
    generada = generar("Concreto hecho en obra f'c=150 kg/cm² en firmes", "M3")
    lines = {line.resource_code: line for line in generada.lines}
    assert lines["MAT-CEM"].quantity == pytest.approx(0.300 * 1.03, abs=0.001)
    assert "MAT-ARENA" in lines and "MAT-GRAVA" in lines and "EQ-REVOLVEDORA" in lines
    premezclado = generar("Concreto premezclado f'c=300 kg/cm² en trabes", "M3")
    assert "MAT-CONC300" in {line.resource_code for line in premezclado.lines}
    assert "MAT-CONC300" in {i.code for i in premezclado.insumos_nuevos}


def test_dala_takes_volume_from_its_section_and_pipe_from_its_diameter():
    dala = generar("Cadena o dala de concreto armado 15x20 cm", "M")
    lines = {line.resource_code: line for line in dala.lines}
    assert lines["MAT-CONC150"].quantity == pytest.approx(0.15 * 0.20 * 1.05, abs=0.0005)
    assert lines["MAT-CIMBRA"].quantity == pytest.approx(0.40)
    tubo = generar("Tubería de PVC sanitario de 100 mm", "M")
    codes = {line.resource_code for line in tubo.lines}
    assert "MAT-TUBO-PVC-SAN-100" in codes and "CUAD-PLOM-1x1" in codes


def test_evaluator_is_arithmetic_only():
    assert evaluar("2*(b_cm+h_cm)/(b_cm*h_cm)*100", {"b_cm": 30, "h_cm": 40}) == (
        pytest.approx(11.6667, abs=0.0005)
    )
    assert evaluar("cemento_ton(fc)", {"fc": 250}) == pytest.approx(0.380)
    assert evaluar("max(espesor_cm, 5) / 100", {"espesor_cm": 3}) == 0.05
    with pytest.raises(ValueError):
        evaluar("__import__('os').system('true')", {})
    with pytest.raises(ValueError):
        evaluar("b_cm.real", {"b_cm": 1})
    with pytest.raises(ValueError):
        evaluar("fc", {})  # variable sin valor
