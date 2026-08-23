from klave_engine.costing.letras import pesos_con_letra


def test_pesos_con_letra_covers_the_forms_tenders_use():
    assert pesos_con_letra(0) == "CERO PESOS 00/100 M.N."
    assert pesos_con_letra(1) == "UN PESOS 00/100 M.N."
    assert pesos_con_letra(21.5) == "VEINTIÚN PESOS 50/100 M.N."
    assert pesos_con_letra(100) == "CIEN PESOS 00/100 M.N."
    assert pesos_con_letra(115.07) == "CIENTO QUINCE PESOS 07/100 M.N."
    assert pesos_con_letra(1234.56) == "UN MIL DOSCIENTOS TREINTA Y CUATRO PESOS 56/100 M.N."
    assert pesos_con_letra(2000) == "DOS MIL PESOS 00/100 M.N."
    assert pesos_con_letra(1_000_000) == "UN MILLÓN PESOS 00/100 M.N."
    assert (
        pesos_con_letra(7_442_142.60)
        == "SIETE MILLONES CUATROCIENTOS CUARENTA Y DOS MIL CIENTO CUARENTA Y DOS PESOS 60/100 M.N."
    )
    assert pesos_con_letra(13_386.19).startswith("TRECE MIL TRESCIENTOS OCHENTA Y SEIS PESOS 19")
    assert pesos_con_letra(0.005) == "CERO PESOS 01/100 M.N."  # half-up like the tender
