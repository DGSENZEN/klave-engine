"""La gramática de las marcas (R67): una sola para todos los lectores y para el bloqueo de la IA."""

import pytest
from klave_engine.detection.text_patterns import TextPatternConfig
from klave_engine.estructura.marcas import extremos_de_rango, leer_marcas, marca_en_rango

C = TextPatternConfig()


@pytest.mark.parametrize(
    "texto,tipo,piezas",
    [
        # Una sola marca, acotada: se lee.
        ("K-1", "unica", ["K-1"]),
        ("K-1.1", "unica", ["K-1.1"]),
        ("K-15A", "unica", ["K-15A"]),
        ("K-15A.1 4#3", "unica", ["K-15A.1"]),
        ("T1-1 4#3", "unica", ["T1-1"]),
        ("K-1-A 4#3", "unica", ["K-1-A"]),
        ("D-X", "unica", ["D-X"]),
        ("K15A 4#3", "unica", ["K15A"]),  # como la escribe la etiqueta
        ("K-1. 4#3", "unica", ["K-1"]),  # el punto final antes de un espacio acota
        ("(K-7) 4#3", "unica", ["K-7"]),
        ("TRABE:T-1 E#3@1S", "unica", ["T-1"]),
        ("TRABE T 1 E#3@1S", "unica", ["T-1"]),
        ("TRABE T - 1 E#3@1S", "unica", ["T-1"]),
        ("3.- K 7 E#3@1S", "unica", ["K-7"]),  # a las cifras les sigue un espacio
        ("K-1 15X20 4#3 IGUAL A K-2", "unica", ["K-1"]),  # una referencia no es otra marca
        # Una cuenta de varillas no es una marca.
        ("P 4#3", "ninguna", []),
        ("E#2@15 VER CORTE C-2", "ninguna", []),
        ("2E#3EXT@10", "ninguna", []),
        ("CENTRO@20", "ninguna", []),
        # Listas y rangos, con o sin espacios: se reportan como se escribieron.
        ("K-1 Y K-2 15X20", "varias", ["K-1", "K-2"]),
        ("K-1, K-2 4#3", "varias", ["K-1", "K-2"]),
        ("T-1=T-2 E#3@1S", "varias", ["T-1", "T-2"]),
        ("T-1+T-2", "varias", ["T-1", "T-2"]),
        ("T-1&T-2", "varias", ["T-1", "T-2"]),
        ("K-1 A K-4 4#3", "varias", ["K-1 A K-4"]),
        ("DE K-1 A K-4 4#3", "varias", ["DE K-1 A K-4"]),
        ("K-1 A 4 4#3", "varias", ["K-1 A 4"]),
        ("K-1 HASTA K-4", "varias", ["K-1 HASTA K-4"]),
        ("K-1-K-3 4#3", "varias", ["K-1-K-3"]),
        ("K-1–K-3 4#3", "varias", ["K-1–K-3"]),
        ("K-1-A-K-3 4#3", "varias", ["K-1-A-K-3"]),
        ("T1-1 A T1-3", "varias", ["T1-1 A T1-3"]),
        ("T1-1-T1-3", "varias", ["T1-1-T1-3"]),
        ("K-1 A C-4", "varias", ["K-1 A C-4"]),
        # Pegada a algo: ambigua, con cada prefijo que es una marca (y el rango si sigue «-n»).
        ("T2-20X40", "ambigua", ["T2", "T2-20"]),
        ("T2-15E#3@15 20X40", "ambigua", ["T2", "T2-15", "T2-15E"]),
        ("T1-4#3 E#2@20", "ambigua", ["T1", "T1-4"]),
        ("K-7E#3@20 15X20", "ambigua", ["K-7", "K-7E"]),
        ("T1-1E#3@20 20X40", "ambigua", ["T1", "T1-1", "T1-1E"]),
        ("K-1-3 4#3", "ambigua", ["K-1", "K-1 A K-3"]),
        ("K7E#3@1S", "ambigua", ["K7", "K7E"]),
        ("K-15E#3@20", "ambigua", ["K-15", "K-15E"]),  # nunca K-1: le sigue una cifra
        ("P-5-P 4#3", "ambigua", ["P-5"]),  # «P 4» es una cuenta, no P-4
        ("T-1-T 4#3", "ambigua", ["T-1"]),
        ("C-1-P 4#3", "ambigua", ["C-1"]),
        ("K-1-CE 4#3", "ambigua", ["K-1"]),
        ("4#3-K-7", "ambigua", ["K-7"]),
    ],
)
def test_the_mark_grammar(texto, tipo, piezas):
    lectura = leer_marcas(texto, C)
    assert (lectura.tipo, lectura.piezas) == (tipo, piezas)
    assert (lectura.marca == piezas[0]) if tipo == "unica" else lectura.marca is None


@pytest.mark.parametrize(
    "rango,extremos,dentro,fuera",
    [
        ("K-1 A K-4", ["K-1", "K-4"], ["K-2", "K-2A", "K-4A"], ["K-5", "C-2"]),
        ("K-1 A 4", ["K-1", "K-4"], ["K-3"], ["K-5"]),
        ("T1-1 A T1-3", ["T1-1", "T1-3"], ["T1-2"], ["T-2", "T1-4"]),
        ("T1-1-T1-3", ["T1-1", "T1-3"], ["T1-2"], ["T1-4"]),
        ("T1-1 A 3", ["T1-1", "T1-3"], ["T1-2", "T1-3"], ["T-3"]),  # el fin cambia el último número
        ("K-1-K-3", ["K-1", "K-3"], ["K-2"], ["K-4"]),
        ("K-1 A C-4", ["K-1", "C-4"], ["C-4"], ["K-2", "C-2"]),  # letras distintas: sólo extremos
    ],
)
def test_range_ends_and_between(rango, extremos, dentro, fuera):
    assert extremos_de_rango(rango, C) == extremos
    assert all(marca_en_rango(rango, m, C) for m in dentro)
    assert not any(marca_en_rango(rango, m, C) for m in fuera)
