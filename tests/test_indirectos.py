"""Desglose de indirectos: la aritmética del documento, a mano."""

from klave_engine.costing.indirectos import (
    AnalisisFinanciamiento,
    DesgloseCampo,
    DesgloseOficinaCentral,
    RubroIndirecto,
    documenta_campo,
    documenta_oficina,
)


def test_campo_mensual_por_meses_y_unicos_una_vez():
    desglose = DesgloseCampo(rubros=[
        RubroIndirecto(concepto="Renta de bodega", categoria="depreciacion_mantenimiento_rentas",
                       importe=10_000.0, base="mensual"),
        RubroIndirecto(concepto="Fianza de cumplimiento", categoria="seguros_fianzas",
                       importe=30_000.0, base="unico"),
    ])
    doc = documenta_campo(desglose, meses=6, plantilla_total=120_000.0, cargos_sin_sueldo=0)
    # 10,000 × 6 + 30,000 + 120,000 de plantilla = 210,000
    assert doc.total == 210_000.0
    personal = doc.renglones[0]
    assert personal.fuente == "plantilla de campo" and personal.importe == 120_000.0
    assert not any(r.sin_capturar for r in doc.renglones)


def test_campo_rubro_sin_importe_queda_visible_y_fuera_del_total():
    desglose = DesgloseCampo(rubros=[
        RubroIndirecto(concepto="Renta de bodega", importe=10_000.0, base="mensual"),
        RubroIndirecto(concepto="Vehículo de residente", importe=0.0, base="mensual"),
    ])
    doc = documenta_campo(desglose, meses=3, plantilla_total=0.0, cargos_sin_sueldo=0)
    assert doc.total == 30_000.0  # el rubro sin capturar no suma
    vacio = next(r for r in doc.renglones if r.concepto == "Vehículo de residente")
    assert vacio.sin_capturar and vacio.importe == 0.0
    assert any("sin importe capturado" in n for n in doc.notas)


def test_campo_plantilla_incompleta_se_dice():
    doc = documenta_campo(DesgloseCampo(), meses=4, plantilla_total=80_000.0, cargos_sin_sueldo=2)
    assert doc.total == 80_000.0
    assert any("sin sueldo" in n for n in doc.notas)


def test_oficina_prorratea_por_volumen_anual():
    oficina = DesgloseOficinaCentral(
        rubros=[RubroIndirecto(concepto="Renta de oficina", importe=600_000.0),
                RubroIndirecto(concepto="Nómina administrativa", importe=1_400_000.0)],
        volumen_anual_contratado=40_000_000.0,
    )
    doc = documenta_oficina(oficina, costo_directo=10_000_000.0)
    # 2,000,000 / 40,000,000 = 5 % → 500,000 en esta obra
    assert doc is not None and doc.total == 500_000.0
    assert any("5.0000 %" in n for n in doc.notas)


def test_oficina_sin_volumen_no_hay_analisis():
    oficina = DesgloseOficinaCentral(
        rubros=[RubroIndirecto(concepto="Renta", importe=600_000.0)],
        volumen_anual_contratado=0.0,
    )
    assert documenta_oficina(oficina, costo_directo=10_000_000.0) is None


def test_financiamiento_faltantes_nombra_lo_que_falta():
    a = AnalisisFinanciamiento(tasa_anual=12.0, indicador="TIIE 28 días")
    assert not a.completo
    assert a.faltantes() == ["fuente", "fecha de publicación"]
    b = AnalisisFinanciamiento(tasa_anual=12.0, indicador="TIIE 28 días",
                               fuente="Banxico SF43783", fecha_publicacion="2026-08-27")
    assert b.completo and b.faltantes() == []
