"""Ranking the taller's catálogo against an engine concept: units gate, words
score, specs decide, and every score says why."""

from klave_engine.costing.matching import (
    Candidate,
    partida_de,
    rank,
    score,
    split_alcance,
    unit_key,
)
from klave_engine.costing.sources.cdmx_capitulos import seccion_de


def _c(clave, description, unit, price=100.0, kind="reference"):
    return Candidate(kind=kind, key=clave, clave=clave, description=description, unit=unit,
                     price=price, source="Catálogo propio")


def test_units_are_a_gate_and_specs_decide():
    concept = "Castillos y columnas de concreto armado f'c=250 kg/cm²"
    candidates = [
        _c("EST-C-250",
           "Castillo de concreto f'c=250 kg/cm2 armado con 4 vars #3, sección 15x20", "M3"),
        _c("EST-C-200", "Castillo de concreto f'c=200 kg/cm2 armado, sección 15x20", "M3"),
        _c("EST-C-M", "Castillo de concreto f'c=250 kg/cm2 por metro lineal", "M"),
        _c("MUR-001", "Muro de block de concreto 15x20x40 asentado con mortero", "M3"),
    ]
    ranked = rank(concept, "M3", candidates)
    assert [m.candidate.clave for m in ranked][:2] == ["EST-C-250", "EST-C-200"]
    assert ranked[0].score > ranked[1].score + 0.2  # f'c mismatch costs a lot
    assert any("f'c=250 coincide" in r for r in ranked[0].reasons)
    assert all(m.candidate.clave != "EST-C-M" for m in ranked)  # M never matches M3
    wall = next((m for m in ranked if m.candidate.clave == "MUR-001"), None)
    assert wall is None or wall.score < 0.3  # another family


def test_unit_keys_normalise_the_usual_spellings():
    assert unit_key("m²") == "M2" and unit_key("M2") == "M2" and unit_key("ml") == "M"
    assert unit_key("Pieza") == "PZA" and unit_key("pza.") == "PZA"


def test_score_explains_shared_words_and_family():
    match = score(
        "Muros de block/concreto, incluye refuerzo y mortero", "M2",
        _c("MUR-015", "Muro de block hueco de concreto 15x20x40 cm asentado con mortero 1:4", "M2"),
        phase="Albañilería",
    )
    assert match is not None and match.score >= 0.6
    assert any("misma familia: block" in r or "muro" in r for r in match.reasons)


def test_head_noun_negatives_and_thickness():
    # An aplanado is not a muro that includes aplanado; a demolición is not a losa.
    covintec = score(
        "Aplanado de mezcla cemento-arena 1:4 en muros, acabado fino, ambas caras", "M2",
        _c("MUR-COV", "Muro de 11 cm de espesor con panel Covintec, aplanado fino de mezcla "
           "cemento arena en ambas caras", "M2"),
    )
    assert covintec is not None and covintec.score < 0.45
    assert any("es un(a) muro" in r for r in covintec.reasons)
    demolition = score(
        "Losa maciza de concreto armado f'c=250", "M3",
        _c("DEM-061", "Demolición de losa de concreto armado a mano con marro y cincel", "M3"),
    )
    assert demolition is None or demolition.score < 0.2
    # Thickness is a spec: a firme de 8 cm is not the firme de 10 cm.
    firme10 = score("Firme de concreto f'c=150 de 10 cm, acabado pulido", "M2",
                    _c("F10", "Firme de 10 cm de espesor de concreto f'c=150 pulido", "M2"))
    firme8 = score("Firme de concreto f'c=150 de 10 cm, acabado pulido", "M2",
                   _c("F8", "Firme de 8 cm de espesor de concreto f'c=150 pulido", "M2"))
    assert firme10 and firme8 and firme10.score > firme8.score + 0.2


# ------------------------------------------- normalización del catálogo ----


def test_el_alcance_no_pesa_como_la_identidad():
    """Un renglón mexicano se escribe «<concepto>, incluye: <alcances>». Lo de
    antes dice qué es; lo de después, hasta dónde llega el precio. Mezclarlos
    hace que «cople, etiqueta verde» pesen tanto como «tubo conduit»."""
    identidad, alcance = split_alcance(
        'tubo conduit galvanizado de 13 mm, incluye: cople, etiqueta verde'
    )
    assert identidad == "tubo conduit galvanizado de 13 mm"
    assert alcance == "cople, etiqueta verde"
    # Sin cláusula, todo es identidad.
    assert split_alcance("Muro de block") == ("Muro de block", "")


def test_el_verbo_con_el_que_abre_un_renglon_no_lo_identifica():
    """«Suministro y colocación de tubo conduit» y «Canalización con tubo
    conduit» son el mismo concepto y no comparten el verbo."""
    publicado = _c("EL01", "Suministro y colocación de tubo conduit galvanizado de 13 mm", "M")
    m = score("Canalización con tubo conduit, incluye accesorios", "M", publicado,
              "Instalación eléctrica")
    assert m is not None and m.score > 0.4


def test_ramaleo_y_tuberia_son_la_misma_familia():
    """El sinónimo tiene que valer también para la familia y la cabeza, no
    sólo para las palabras sueltas: cuando sólo valía para las palabras, un
    «ramaleo a base de tubería» se llevaba el castigo de ser otra cosa y
    desaparecía de los candidatos."""
    m = score(
        "Tubería de agua caliente con aislamiento", "M",
        _c("R1", "RAMALEO A BASE DE TUBERIA DE POLIPROPILENO DE 13 MM", "M"),
        "Instalación hidráulica",
    )
    assert m is not None
    assert not any("no un(a)" in r for r in m.reasons)


def test_la_partida_del_renglon_es_lo_que_dice_no_donde_lo_archivaron():
    """Un taller archiva «ramaleo de tubería» bajo ALB porque ranurar el muro
    es trabajo de albañil, y eso no lo vuelve albañilería cuando se le busca
    precio a una tubería."""
    assert partida_de("1-ALB-LIM-075", "RAMALEO A BASE DE TUBERIA DE POLIPROPILENO") == (
        "hidraulica"
    )
    # Sin nada que lo diga, el prefijo sí sugiere.
    assert partida_de("1-ALB-GEN-001", "Renglón sin señas") == "albanileria"
    assert partida_de("SIN-CLAVE", "Renglón sin señas") == ""


def test_una_partida_distinta_descarta_el_renglon():
    """«Alimentación eléctrica … protegida con tubo» ganaba sobre una tubería
    de gas por compartir la palabra tubo."""
    m = score(
        "Tubería de gas, incluye conexiones y prueba de hermeticidad", "M",
        _c("E9", "ALIMENTACION ELECTRICA DE CENTRO DE CARGA PROTEGIDA CON TUBO", "M"),
        "Instalación de gas",
    )
    assert m is None or any("otra partida" in r for r in m.reasons)


def test_un_preparativo_no_es_la_cosa_que_prepara():
    """Una «ranura para alojar tubería» no es tubería."""
    m = score(
        "Tubería de agua fría, incluye conexiones", "M",
        _c("R9", 'RANURA PARA ALOJAR TUBERÍA HASTA DE 3/4" EN MURO', "M"),
        "Instalación hidráulica",
    )
    assert m is None or any("no un(a) tuberia" in r for r in m.reasons)


# ------------------------------------ la nomenclatura del tabulador --------


def test_la_seccion_del_tabulador_declara_la_partida():
    """El Tabulador CDMX organiza sus renglones en secciones de dos letras y
    la clave de cada uno empieza por la de la suya. Eso lo declara el
    publicador: no hay heurística de texto que le compita."""
    assert seccion_de("IB12BB") == (
        "hidraulica", "Suministro, instalación y pruebas de tubos y conexiones de cobre"
    )
    assert seccion_de("KE14BC")[0] == "electrica"
    assert seccion_de("JQ11AA")[0] == "aire"
    assert seccion_de("CG17BB")[0] == "canceleria"
    assert seccion_de("GS20BB")[0] == "impermeabilizacion"
    assert seccion_de("ZZ99ZZ") is None


def test_la_seccion_gana_sobre_lo_que_el_texto_parece_decir():
    """«Codo de 45°» no dice de qué instalación es; su sección sí."""
    assert partida_de("IB16HE", "Codo de 45° X 20 mm de diámetro") == "hidraulica"
    assert partida_de("KE16HE", "Codo de 45° X 20 mm de diámetro") == "electrica"


def test_la_seccion_completa_lo_que_el_renglon_telegrafico_calla():
    """Un renglón sin familia propia hereda la de su encabezado; uno que ya se
    nombra solo no, porque meterle las palabras del capítulo lo diluye."""
    telegrafico = _c("IB23BE", 'Ye de 19 mm (3/4") de diámetro', "PZA")
    m = score("Conexión de cobre para agua fría", "PZA", telegrafico,
              "Instalación hidráulica")
    assert m is not None and m.score > 0.2


def test_la_seccion_corrobora_sin_meterse_en_la_descripcion():
    m = score(
        "Canalización con tubo conduit, incluye accesorios", "M",
        _c("KE12BB", "Suministro y colocación de tubo conduit galvanizado de 13 mm", "M"),
        "Instalación eléctrica",
    )
    assert m is not None
    assert any("la sección lo confirma" in r for r in m.reasons)


def test_el_material_encabezando_nombra_lo_mismo_que_el_elemento():
    """Los catálogos mexicanos usan los dos órdenes: el tabulador encabeza por
    el material —«concreto hidráulico f'c=250 en columnas»— y el catálogo de
    un taller por el elemento —«columnas de concreto armado». Es el mismo
    concepto y el castigo de cabeza distinta lo estaba matando."""
    m = score(
        "Columnas y castillos de concreto armado f'c=250 kg/cm²", "M3",
        _c("FG16CB", "Suministro y colocación de concreto hidráulico f'c=250 kg/cm2 "
                     "en columnas", "M3"),
        "Estructura",
    )
    assert m is not None
    assert not any("no un(a)" in r for r in m.reasons)
    assert any("al revés" in r for r in m.reasons)


def test_dos_trabajos_distintos_siguen_siendo_distintos():
    """La regla del orden vale sólo cuando uno de los dos encabezados es un
    material. Aplanado y muro son los dos trabajos, se pagan por separado, y
    «muro con aplanado» sigue sin ser «aplanado en muros»."""
    m = score(
        "Aplanado de mezcla cemento-arena 1:4 en muros, acabado fino, ambas caras", "M2",
        _c("MUR-COV", "Muro de 11 cm de espesor con panel Covintec, aplanado fino de "
                      "mezcla cemento arena en ambas caras", "M2"),
    )
    assert m is not None
    assert any("es un(a) muro" in r for r in m.reasons)
    assert not any("al revés" in r for r in m.reasons)
    assert m.score < 0.45


def test_el_orden_invertido_pide_que_los_dos_digan_las_dos_cosas():
    """«Concreto hidráulico f'c=250» a secas no es la columna: para valer al
    revés, el renglón tiene que nombrar también el elemento."""
    m = score(
        "Columnas y castillos de concreto armado f'c=250", "M3",
        _c("FE12BB", "Suministro y colocación de concreto hidráulico f'c=250", "M3"),
        "Estructura",
    )
    assert m is None or not any("al revés" in r for r in m.reasons)
