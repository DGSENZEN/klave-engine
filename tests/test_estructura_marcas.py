"""La gramática de las marcas (R67): una sola para todos los lectores y para el bloqueo de la IA."""

import pytest
from klave_engine.detection.text_patterns import TextPatternConfig
from klave_engine.estructura.marcas import (
    extremos_de_rango,
    leer_marcas,
    marca_en_rango,
    titulos,
)

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
        # R68.2: una cuenta de varillas no es una marca (la que el parser lee como grupo, y la
        # que lleva la palabra de la varilla delante). V-1 sin «#» tras su número sí lo es.
        ("V4 #4", "ninguna", []),
        ("V12 #5", "ninguna", []),
        ("V12 #5 E#3 @20CMS", "ninguna", []),
        ("DALA 15X20 V4 #4 E#2@20", "ninguna", []),
        ("V4#4 E#3", "ninguna", []),
        ("CR-1 V4 #4 E#3 @20CMS", "unica", ["CR-1"]),
        ("K 7 #3", "ninguna", []),  # el parser lee 7#3
        ("K-1, 4#3", "unica", ["K-1"]),  # ni una lista
        ("V-1 4#4", "unica", ["V-1"]),
        ("V-1 15X20", "unica", ["V-1"]),
        ("K-7 #3", "unica", ["K-7"]),  # «7 #3» no es un grupo que el parser tome
        # R68.3: delante de una marca con espacios, cualquier cosa que no sea una letra.
        ("3.-K 7 15X20 4#3", "unica", ["K-7"]),
        ("1.-K 7 E#3@1S", "unica", ["K-7"]),
        ('"K 7" E#3@1S', "unica", ["K-7"]),
        ("TRABE-T 1 E#3@1S", "unica", ["T-1"]),
        ("K-1/K 7 4#3", "varias", ["K-1", "K-7"]),
        ("K-1-K 3 4#3", "varias", ["K-1-K-3"]),
        # R68.4: las etiquetas de la configuración también empiezan una marca pegada.
        ("TL-1E#3@20 20X40", "ambigua", ["TL-1", "TL-1E"]),
        ("V-1E#3@20 20X40", "ambigua", ["V-1"]),
        # R68.5: la letra de una cabeza de estribo antes de «#» no es la de una variante.
        ("K-7-E #3@20 15X20", "ambigua", ["K-7", "K-7-E"]),
        ("T-1-E #3@20 20X40", "ambigua", ["T-1", "T-1-E"]),
        ("K-7E #3@20", "ambigua", ["K-7", "K-7E"]),
        ("K-1-E 4#3", "unica", ["K-1-E"]),
        # R68.6: una lista escrita sólo con números.
        ("K-1, 2 Y 3 15X20 4#3", "varias", ["K-1", "K-2", "K-3"]),
        ("K-1 Y 2 15X20", "varias", ["K-1", "K-2"]),
        ("T1-1 Y 2 4#3", "varias", ["T1-1", "T1-2"]),
        # R68.7: los guiones de Unicode son guiones.
        ("K–7 4#3", "unica", ["K-7"]),
        ("K‑7 4#3", "unica", ["K-7"]),
        ("K-1 Y K–2 4#3", "varias", ["K-1", "K-2"]),
        # R68.8: la referencia se lleva su única marca (no se lee; el respaldo la bloquea).
        ("CORTE K-1 15X20 4#3", "ninguna", []),
        ("DET. K-1 4#3", "ninguna", []),
        # R78: una letra suelta tras una marca: ¿su sufijo? Ambigua; no la cabeza de unos
        # estribos ni el conector de un rango o una lista.
        ("K-15 A 4#3 E#3@20", "ambigua", ["K-15", "K-15A", "K-15-A"]),
        ("K-1 A 4#3 E#3@20", "ambigua", ["K-1", "K-1A", "K-1-A"]),
        ("K-15 ARMADO #3", "unica", ["K-15"]),
        ("K-8 E #3@20", "unica", ["K-8"]),
        ("K-1 A K-4 4#3", "varias", ["K-1 A K-4"]),
        # R79: las etiquetas de la configuración escritas con espacio.
        ("TRABE TL 1 20X40 4#3", "unica", ["TL-1"]),
        ("TRABE TE A E#3@20 20X40", "unica", ["TE-A"]),
        ("V 1 4#4", "unica", ["V-1"]),
        ("TE ARMADO #4@20", "ninguna", []),
        # R80: «V-4 #4»: ¿la marca V-4 o una cuenta de varillas?
        ("V-4 #4 E#3@20", "ambigua", ["V-4"]),
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


@pytest.mark.parametrize(
    "texto,marcas",
    [
        ("CORTE K-1 15X20 4#3", ["K-1"]),
        ("DET. K-1 4#3", ["K-1"]),
        ("DETALLE T1-1 20X40", ["T1-1"]),
        ("E#2@15 VER CORTE C-2", []),  # remite a otra parte: no es un título
        ("2E#3 VER CORTE", []),
        ("K-1 4#3", []),
    ],
)
def test_the_marks_a_title_names(texto, marcas):
    assert titulos(texto, C) == marcas


@pytest.mark.parametrize(
    "texto,tipo,piezas",
    [
        # R85: el fin de un rango o de una lista es una marca o un entero sin unidad, sin «X»,
        # «#», «@» ni decimales; si no, la letra suelta es ambigua (R78).
        ("K-15 A 20X20 4#3 E#3@20", "ambigua", ["K-15", "K-15A", "K-15-A"]),
        ("K-1 A 15X20", "ambigua", ["K-1", "K-1A", "K-1-A"]),
        ("CASTILLOS K-1 A 3.00 M MAX 15X15 4#3 E#2@20", "ambigua", ["K-1", "K-1A", "K-1-A"]),
        ("C-1 A 20 CM E#3@1S", "ambigua", ["C-1", "C-1A", "C-1-A"]),
        ("K-1 A 4", "varias", ["K-1 A 4"]),
        ("K-1 A 4A", "varias", ["K-1 A 4A"]),
        ("K-1, 2 Y 3 15X20 4#3", "varias", ["K-1", "K-2", "K-3"]),
    ],
)
def test_a_range_end_is_a_mark_or_a_bare_integer(texto, tipo, piezas):
    lectura = leer_marcas(texto, C)
    assert (lectura.tipo, lectura.piezas) == (tipo, piezas)
