"""El diámetro nominal: lo que separa «tubería de agua fría» —que nadie
cotiza— de un concepto con precio publicado."""

from klave_engine.costing.matching import Candidate, score
from klave_engine.detection.instalaciones_symbols import NOMINALES, normaliza_diametro


def _c(clave: str, descripcion: str, unidad: str = "M") -> Candidate:
    return Candidate(kind="reference", key=clave, clave=clave, description=descripcion,
                     unit=unidad, price=100.0)


def test_el_plano_dice_pulgadas_y_la_publicacion_milimetros():
    """Media pulgada son 12.7 mm y a esa tubería todo el mundo le dice de 13:
    no es una conversión aritmética, es la tabla de diámetros nominales."""
    assert normaliza_diametro('AF-1/2"Ø') == (13, '13 mm (1/2")')
    assert normaliza_diametro('AC-3/4"Ø') == (19, '19 mm (3/4")')
    assert normaliza_diametro('4"Ø') == (102, '102 mm (4")')
    assert normaliza_diametro('2 1/2"') == (64, '64 mm (2 1/2")')


def test_los_milimetros_del_plano_se_llevan_al_nominal_publicado():
    """El comercio escribe 100 y el tabulador 102; son el mismo tubo de 4."""
    assert normaliza_diametro("TUBERÍA DE PEAD 19MM") == (19, '19 mm (3/4")')
    assert normaliza_diametro("100 mm") == (102, '102 mm (4")')
    assert normaliza_diametro("Ø 32") == (32, '32 mm (1 1/4")')


def test_un_numero_que_no_es_un_diametro_no_se_fuerza_a_serlo():
    assert normaliza_diametro('16" x 16"') is None  # sección de ducto
    assert normaliza_diametro("sin nada") is None
    assert normaliza_diametro("") is None


def test_la_tabla_nominal_va_de_menor_a_mayor_y_no_repite():
    mm = [m for m, _ in NOMINALES]
    assert mm == sorted(mm) and len(mm) == len(set(mm))


# --------------------------------------------- el diámetro que empareja ----


def test_el_diametro_elige_entre_medidas_del_mismo_concepto():
    """Aquí está el valor: un tabulador publica el mismo concepto en seis
    medidas, todas con las mismas palabras. Sin diámetro las seis empatan y
    gana cualquiera; con él gana la del plano."""
    from klave_engine.costing.matching import rank

    medidas = [
        _c(f"KE15B{letra}",
           f'Suministro y colocación de tubo conduit galvanizado de {mm} mm ({pulg}")')
        for letra, mm, pulg in
        [("B", 13, "1/2"), ("C", 19, "3/4"), ("D", 25, "1"), ("E", 32, "1 1/4")]
    ]
    nuestro = "Canalización con tubo conduit, incluye accesorios y soportería"

    sin = rank(nuestro, "M", medidas, phase="Instalación eléctrica", limit=4)
    assert len({round(m.score, 2) for m in sin}) == 1, "sin diámetro las cuatro empatan"

    for mm, pulg in [(13, "1/2"), (25, "1")]:
        con = rank(f'Canalización con tubo conduit de {mm} mm ({pulg}"), incluye accesorios',
                   "M", medidas, phase="Instalación eléctrica", limit=1)
        assert f"{mm} mm" in con[0].candidate.description
        assert any(f"diámetro {mm} mm coincide" in r for r in con[0].reasons)


def test_el_diametro_del_plano_sube_al_renglon_que_le_toca():
    conduit = _c("KE15BD", "Suministro y colocación de tubo conduit galvanizado de 13 mm (1/2\")")
    con = score(
        'Canalización con tubo conduit de 13 mm (1/2"), incluye accesorios y soportería',
        "M", conduit, "Instalación eléctrica",
    )
    assert con is not None and con.score >= 0.9
    assert any("diámetro 13 mm coincide" in r for r in con.reasons)


def test_un_tubo_de_media_pulgada_no_es_uno_de_cuatro():
    """Pesa como la f'c porque decide igual de fuerte: es otro concepto."""
    m = score(
        'Tubería sanitaria de albañal de 102 mm (4")', "M",
        _c("HB12BB", 'Tubo de pvc tipo sanitario de 13 mm (1/2") de diámetro'),
        "Instalación sanitaria",
    )
    assert m is None or any("diámetro distinto" in r for r in m.reasons)


def test_el_diametro_cuenta_solo_si_esta_en_la_identidad():
    """Después de «incluye:» es alcance, y el alcance no identifica nada."""
    from klave_engine.costing.matching import profile

    dentro = profile('Tubería de gas de 19 mm (3/4"), incluye conexiones')
    fuera = profile('Tubería de gas, incluye conexiones de 19 mm (3/4")')
    assert dentro.specs["diam"] == {"19"}
    assert fuera.specs["diam"] == set()


def test_un_conduit_es_un_tubo_y_no_se_acusan_de_ser_distintos():
    """Ponerlos en familias separadas hacía que «canalización con tubo
    conduit» y «tubo poliducto» se descartaran mutuamente."""
    m = score(
        "Canalización con tubo conduit", "M",
        _c("KF12BD", 'Suministro y colocación de tubo poliducto de 13 mm (1/2")'),
        "Instalación eléctrica",
    )
    assert m is not None
    assert not any("no un(a)" in r for r in m.reasons)


# ------------------------------------------------------- el material -------


def test_el_material_declarado_descarta_al_de_otro_material():
    """El metro de cobre cuesta el doble que el de PP-R al mismo diámetro:
    materiales distintos son conceptos distintos, no un matiz."""
    cobre = _c("JL12BF", 'Tubo de cobre flexible, de 19 mm (3/4") de diámetro')
    m = score('Tubería de gas de PEAD de 19 mm (3/4"), incluye conexiones', "M",
              cobre, "Instalación de gas")
    assert m is None or any("material distinto" in r for r in m.reasons)


def test_no_declarar_material_no_castiga_a_nadie():
    """Un rótulo «AF-1/2"Ø» dice sistema y diámetro; el material se queda en
    la simbología. No declarar es lo normal, no un defecto."""
    cobre = _c("IB12BD", 'Suministro de tubo de cobre tipo "M" de 13 mm (1/2")')
    m = score('Tubería de agua caliente de 13 mm (1/2") con aislamiento', "M",
              cobre, "Instalación hidráulica")
    assert m is not None
    assert not any("material distinto" in r for r in m.reasons)


def test_el_material_no_suma_cuando_coincide():
    """«Cobre» ya suma como palabra compartida: un bono aparte contaría lo
    mismo dos veces, y en los conceptos de concreto —donde la palabra está en
    todos lados— inflaría todo por igual."""
    a = score('Tubería de cobre de 13 mm (1/2")', "M",
              _c("IB1", 'Tubo de cobre tipo "M" de 13 mm (1/2")'), "Instalación hidráulica")
    assert a is not None
    assert not any("material" in r for r in a.reasons)


def test_el_tubo_de_concreto_de_las_redes_no_es_tuberia_domestica():
    """El renglón que se colaba como precio de agua potable: «Instalación de
    tubo de concreto tensado». Si el plano declara cobre, se descarta."""
    concreto = _c("OD15DO", "Instalación de tubo de concreto tensado previamente")
    m = score('Tubería de agua fría de cobre de 25 mm (1")', "M",
              concreto, "Instalación hidráulica")
    assert m is None or any("material distinto" in r for r in m.reasons)
