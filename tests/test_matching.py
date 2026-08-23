"""Ranking the taller's catálogo against an engine concept: units gate, words
score, specs decide, and every score says why."""

from klave_engine.costing.matching import Candidate, rank, score, unit_key


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
