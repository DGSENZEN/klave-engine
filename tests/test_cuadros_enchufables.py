"""La cadena de cuadros acepta lectores por disciplina (S4): un lector
externo entra con rango de cuadro; sin lectores, nada cambia."""

from klave_engine.detection.schedules import ElementSpec, build_schedule_inventory


def _lector(_entities):
    return [
        ElementSpec(
            mark="CA-1", family="canceleria", source="cuadro",
            source_text="CUADRO DE CANCELERÍA: CA-1 1.20×1.50", confidence=0.9,
        )
    ]


def test_un_lector_externo_entra_con_rango_de_cuadro():
    con = build_schedule_inventory([], extra_readers=[_lector])
    assert "CA-1" in con.by_mark
    assert con.by_mark["CA-1"].source == "cuadro"

    sin = build_schedule_inventory([])
    assert sin.by_mark == {}
