"""La nomenclatura del Tabulador CDMX, extraída de los encabezados del propio
PDF: 155 secciones con su título y su partida."""

import re

from klave_engine.costing.sources.cdmx_capitulos import SECCIONES, seccion_de

PARTIDAS = {
    "preliminares", "terracerias", "cimentacion", "estructura", "albanileria",
    "acabados", "impermeabilizacion", "hidraulica", "sanitaria", "electrica",
    "gas", "aire", "canceleria", "pavimentos", "urbanizacion", "senalamiento",
    "jardineria", "limpieza", "proteccion",
}


def test_toda_seccion_tiene_clave_de_dos_letras_titulo_y_partida():
    assert len(SECCIONES) > 140
    for clave, (partida, titulo) in SECCIONES.items():
        assert re.fullmatch(r"[A-Z]{2}", clave), clave
        assert partida in PARTIDAS, (clave, partida)
        assert titulo and len(titulo) > 3, clave


def test_ninguna_seccion_arrastra_la_coletilla_normativa():
    """Casi todos los encabezados terminan en «Norma de Construcción de la
    Administración Pública…», idéntica en todos: se repite y no distingue
    nada, así que no debe quedar dentro del título."""
    for clave, (_partida, titulo) in SECCIONES.items():
        assert "Norma de Construcc" not in titulo, clave
        assert "incluye:" not in titulo.lower(), clave


def test_la_seccion_se_lee_del_prefijo_de_la_clave():
    assert seccion_de("IB12BB")[0] == "hidraulica"
    assert seccion_de("ib12bb")[0] == "hidraulica"  # sin distinguir mayúsculas
    assert seccion_de("") is None
    assert seccion_de("XX00XX") is None


def test_una_clave_que_no_es_del_tabulador_no_tiene_seccion():
    """La clave propia de un taller «ACERO-01» empieza por AC, que en el
    tabulador es «Proyectos». Sin exigir la forma del tabulador, ese renglón
    de acero acabaría clasificado en preliminares."""
    assert seccion_de("ACERO-01") is None
    assert seccion_de("1-ALB-MUR-004") is None
    assert seccion_de("EST-004") is None
    assert seccion_de("IB12BB") is not None


def test_las_secciones_de_instalaciones_estan_donde_deben():
    """Las que hacen falta para ponerle precio a lo que el motor ahora
    detecta."""
    esperado = {
        "IB": "hidraulica",   # tubos y conexiones de cobre
        "IG": "hidraulica",   # tubos de pvc hidráulico
        "HB": "sanitaria",    # tubos de pvc sanitario
        "HI": "hidraulica",   # muebles sanitarios
        "KE": "electrica",    # tubos conduit
        "KL": "electrica",    # accesorios eléctricos
        "JQ": "aire",         # ductos para aire acondicionado
        "JL": "gas",          # instalaciones de gas
        "MB": "canceleria",   # vidrios y cristales
        "CG": "canceleria",   # carpintería, puertas
        "GS": "impermeabilizacion",
    }
    for clave, partida in esperado.items():
        assert clave in SECCIONES, clave
        assert SECCIONES[clave][0] == partida, (clave, SECCIONES[clave])
