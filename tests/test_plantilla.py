"""La plantilla de campo: el único de los cinco programas que no sale del
presupuesto, y las dos honestidades que lo sostienen — un cargo sin sueldo no
vale cero, y la suma tiene que cuadrar contra los indirectos de campo."""

from klave_engine.costing.plantilla import (
    CargoCampo,
    build_personal_tecnico,
    desajuste_de_indirectos,
    plantilla_sugerida,
)


def _cargo(puesto: str, **kw) -> CargoCampo:
    return CargoCampo(puesto=puesto, **kw)


def test_sin_plantilla_el_programa_dice_que_falta_y_por_que():
    """Vacío en silencio es una propuesta desechada; vacío con la razón es un
    pendiente que alguien puede cerrar."""
    programa = build_personal_tecnico([], periods=6, period_days=24, period_label="mes")
    assert programa.renglones == []
    assert programa.total == 0.0
    nota = " ".join(programa.notas)
    assert "45-A-XI-d" in nota and "costo indirecto" in nota


def test_el_cargo_se_reparte_sobre_el_calendario_de_la_obra():
    programa = build_personal_tecnico(
        [_cargo("Superintendente", salario_mensual=45000.0, fsr=1.6)],
        periods=4, period_days=24, period_label="mes",
    )
    renglon = programa.renglones[0]
    assert renglon.unidad == "mes-hombre"
    assert renglon.por_periodo == [1.0, 1.0, 1.0, 1.0]
    assert renglon.cantidad == 4.0
    assert renglon.importe == round(4 * 45000.0 * 1.6, 2)
    assert abs(sum(renglon.importe_por_periodo) - renglon.importe) < 0.01


def test_la_participacion_parcial_se_respeta_en_los_dos_ejes():
    """Un topógrafo a medio tiempo durante los primeros tres meses son 1.5
    meses-hombre, no tres ni seis."""
    programa = build_personal_tecnico(
        [
            _cargo(
                "Topógrafo", salario_mensual=20000.0, fsr=1.0,
                hasta_periodo=3, dedicacion_pct=50.0,
            )
        ],
        periods=6, period_days=24, period_label="mes",
    )
    renglon = programa.renglones[0]
    assert renglon.por_periodo == [0.5, 0.5, 0.5, 0.0, 0.0, 0.0]
    assert renglon.cantidad == 1.5
    assert renglon.importe == round(1.5 * 20000.0, 2)


def test_un_cargo_sin_sueldo_sale_visible_y_sin_importe():
    """No es que ese personal salga gratis: es que nadie capturó lo que gana,
    y el total de abajo está incompleto en esa medida."""
    programa = build_personal_tecnico(
        [
            _cargo("Superintendente", salario_mensual=45000.0, fsr=1.0),
            _cargo("Velador", tipo="servicio"),  # sin sueldo
        ],
        periods=2, period_days=24, period_label="mes",
    )
    velador = next(r for r in programa.renglones if r.puesto == "Velador")
    assert velador.sin_sueldo is True
    assert velador.cantidad == 2.0  # su participación sí se ve
    assert velador.importe == 0.0
    assert programa.cargos_sin_sueldo == 1
    assert any("sin sueldo capturado" in n for n in programa.notas)
    assert any("no es que ese personal salga gratis" in n.lower() for n in programa.notas)


def test_el_periodo_cambia_el_sueldo_del_renglon_no_el_total():
    """Una quincena es media mensualidad: el mismo dinero, otra rejilla."""
    cargos = [_cargo("Residente", salario_mensual=30000.0, fsr=1.0)]
    mensual = build_personal_tecnico(cargos, 6, 24, "mes")
    quincenal = build_personal_tecnico(cargos, 12, 12, "quincena")
    assert quincenal.renglones[0].unidad == "quincena-hombre"
    assert abs(quincenal.total - mensual.total) < 1.0


def test_cuando_cuadra_contra_los_indirectos_de_campo_lo_dice():
    programa = build_personal_tecnico(
        [_cargo("Superintendente", salario_mensual=50000.0, fsr=1.0)],
        periods=4, period_days=24, period_label="mes",
        indirectos_campo=200_000.0,
    )
    assert any("Congruente con la integración" in n for n in programa.notas)


def test_cuando_no_cuadra_lo_dice_con_el_articulo_que_lo_revisa():
    """Los dos números que un revisor pone lado a lado bajo el art. 64-A-I."""
    programa = build_personal_tecnico(
        [_cargo("Superintendente", salario_mensual=50000.0, fsr=1.0)],
        periods=4, period_days=24, period_label="mes",
        indirectos_campo=60_000.0,
    )
    nota = " ".join(programa.notas)
    assert "64-A-I" in nota
    assert "más" in nota  # la plantilla suma más que los indirectos


def test_no_se_compara_mientras_falten_sueldos():
    """Comparar una suma incompleta contra los indirectos produce una alarma
    falsa, y una alarma falsa gasta la atención que hace falta para la real."""
    programa = build_personal_tecnico(
        [
            _cargo("Superintendente", salario_mensual=50000.0, fsr=1.0),
            _cargo("Velador", tipo="servicio"),
        ],
        periods=4, period_days=24, period_label="mes",
        indirectos_campo=60_000.0,
    )
    nota = " ".join(programa.notas)
    assert "64-A-I" not in nota
    assert "todavía no está completa" in nota


def test_un_cargo_fuera_del_calendario_no_aparece():
    programa = build_personal_tecnico(
        [_cargo("Residente", desde_periodo=9, salario_mensual=30000.0)],
        periods=4, period_days=24, period_label="mes",
    )
    assert programa.renglones == []


def test_la_sugerida_propone_puestos_y_no_sueldos():
    """Qué puestos lleva una obra es oficio; cuánto ganan es dinero, y el
    motor no inventa dinero."""
    cargos = plantilla_sugerida(duracion_meses=8.0, frentes=2)
    assert all(c.salario_mensual == 0.0 for c in cargos)
    assert all(c.razon for c in cargos)
    residente = next(c for c in cargos if "Residente" in c.puesto)
    assert residente.cantidad == 2.0  # un residente por frente
    assert "2 frentes" in residente.razon
    puestos = {c.puesto for c in cargos}
    assert "Superintendente de obra" in puestos
    assert "Velador" in puestos
    assert "Ingeniero de costos y estimaciones" in puestos  # obra larga


def test_la_sugerida_de_una_obra_corta_no_carga_puestos_de_una_larga():
    cargos = plantilla_sugerida(duracion_meses=2.0, frentes=1)
    puestos = {c.puesto for c in cargos}
    assert "Ingeniero de costos y estimaciones" not in puestos
    assert "Superintendente de obra" in puestos


def test_no_hay_desajuste_dentro_de_la_tolerancia():
    assert desajuste_de_indirectos(105_000.0, 100_000.0, 0) is None


def test_el_desajuste_se_reporta_con_signo():
    arriba = desajuste_de_indirectos(200_000.0, 100_000.0, 0)
    abajo = desajuste_de_indirectos(50_000.0, 100_000.0, 0)
    assert arriba is not None and arriba > 0
    assert abajo is not None and abajo < 0


def test_una_suma_incompleta_no_levanta_la_alarma():
    """Comparar contra un total al que le faltan sueldos produce una alarma
    falsa, y las falsas son las que enseñan a ignorar la lista."""
    assert desajuste_de_indirectos(200_000.0, 100_000.0, cargos_sin_sueldo=1) is None
