"""Las tablas del plano, la tabla de varillas, las notas numeradas y las reglas del proyecto: lo
que el plano dice, copia por copia."""

import ezdxf
import pytest
from ezdxf.enums import TextEntityAlignment
from klave_engine.dxf.parser import DxfParser
from klave_engine.estructura.armado import NUMEROS
from klave_engine.estructura.asociacion import ancla_texto
from klave_engine.estructura.notas import LIMITE_DE_BLOQUE, leer_notas
from klave_engine.estructura.oraciones import niega, oraciones
from klave_engine.estructura.reglas import (
    ENCABEZADOS_VARILLA,
    RECUBRIMIENTO_SUPUESTO,
    TABLA_ESTANDAR,
    FilaVarilla,
    Reglas,
    leer_reglas,
    leer_tablas_de_varillas,
    numero_de_varilla,
    reglas_estandar,
    tabla_de_varillas,
)
from klave_engine.estructura.tablas import leer_tablas

# La tabla de Marina (orden LA1 LA2 LT1 LT2 LG1 LG2 LG3 r); #10 y #12 no traen LT.
MARINA = {
    "2.5": (30, 30, 30, 40, 20, 10, 5, 4),
    "3": (30, 35, 35, 50, 20, 15, 5, 4),
    "4": (35, 45, 50, 65, 30, 15, 5, 6),
    "5": (40, 60, 60, 80, 35, 20, 10, 7),
    "6": (50, 70, 70, 100, 40, 25, 10, 9),
    "8": (85, 115, 115, 150, 55, 30, 10, 11),
    "10": (130, 180, None, None, 65, 40, 15, 14),
    "12": (185, 255, None, None, 80, 50, 15, 17),
}
CAMPOS = ("LA1", "LA2", "LT1", "LT2", "LG1", "LG2", "LG3", "r")
X_ENCABEZADO = dict(
    zip(
        ENCABEZADOS_VARILLA,
        (-1.65, -0.67, -0.04, 0.63, 1.26, 1.91, 2.55, 3.20, 3.97),
        strict=True,
    )
)
ALTO = 0.12
PASO = 0.25


def _poner(destino, texto, x, y, alinear=True, alto=ALTO, en_la_base=False):
    t = destino.add_text(texto, height=alto)
    if en_la_base:  # esquina inferior izquierda: ``y`` es la base del texto
        t.set_placement((x, y))
    elif alinear:  # como Marina: todo el texto centrado, con punto de alineación
        t.set_placement((x, y), align=TextEntityAlignment.MIDDLE_CENTER)
    else:
        t.set_placement((x, y))


def _bloque(
    doc,
    nombre,
    alinear=True,
    cambio=None,
    sin=(),
    sin_encabezado=(),
    hueco_antes=None,
    desfase=None,
    extra=(),
    nota=True,
    etiquetas=None,
    paso=PASO,
    alto_encabezado=ALTO,
    alto_valores=ALTO,
    alto_numeros=ALTO,
    numeros_en_la_base=False,
    desfase_valores=0.0,
):
    """El bloque de la tabla de Marina: título, encabezado, ``No.``, ``(cm)``, ocho filas y la
    nota de abajo. Las variantes: ``cambio`` {(varilla, campo): texto}, ``sin`` varillas,
    ``sin_encabezado`` fichas, ``hueco_antes`` (varilla, renglones en blanco), ``desfase``
    {(varilla, campo): (dx, dy)}, ``extra`` [(texto, x, y)], ``etiquetas`` {varilla: cómo se
    escribe}, ``paso`` entre renglones, ``alto_encabezado``, ``alto_numeros`` y ``alto_valores``,
    ``numeros_en_la_base`` (los números de varilla en la esquina inferior izquierda y los
    valores centrados: la ``y`` de un valor queda media altura arriba de la del número) y
    ``desfase_valores`` (dy de todos los valores)."""
    cambio = cambio or {}
    desfase = desfase or {}
    etiquetas = etiquetas or {}
    bloque = doc.blocks.new(nombre)
    _poner(bloque, "TABLA No.1", -1.5, 0.55, alinear, alto_encabezado)
    _poner(bloque, "TABLA DE VARILLAS", 0.0, 0.35, alinear, alto_encabezado)
    for encabezado, x in X_ENCABEZADO.items():
        if encabezado not in sin_encabezado:
            _poner(bloque, encabezado, x, 0.0, alinear, alto_encabezado)
    _poner(bloque, "No.", X_ENCABEZADO["VARILLA"], -paso, alinear, alto_encabezado)
    _poner(bloque, "(cm)", 1.6, -paso, alinear, alto_encabezado)
    fila = 0
    corrimiento = 0.0
    for numero, valores in MARINA.items():
        if numero in sin:
            continue
        if hueco_antes and numero == hueco_antes[0]:
            corrimiento = hueco_antes[1] * paso
        fila += 1
        y = -paso - paso * fila - corrimiento
        _poner(
            bloque,
            etiquetas.get(numero, numero),
            X_ENCABEZADO["VARILLA"],
            y,
            alinear,
            alto_numeros,
            en_la_base=numeros_en_la_base,
        )
        for campo, valor in zip(CAMPOS, valores, strict=True):
            valor = cambio.get((numero, campo), valor)
            if valor is not None:
                dx, dy = desfase.get((numero, campo), (0.0, 0.0))
                if numeros_en_la_base:
                    dy += alto_valores / 2
                dy += desfase_valores
                _poner(
                    bloque,
                    str(valor),
                    X_ENCABEZADO[campo] + dx,
                    y + dy,
                    alinear or numeros_en_la_base,
                    alto_valores,
                )
    if nota:  # como en Marina: las leyendas de la tabla, a la izquierda, un poco más abajo
        leyenda = "LA1=LONGITUD DE ANCLAJE PARA VARILLAS CON MENOS DE 30 cm DE CONCRETO"
        bloque.add_text(leyenda, height=0.07).set_placement((-1.9, y - 0.2))
    for texto, x, y in extra:
        _poner(bloque, texto, x, y, alinear)
    return bloque


def _entidades(
    tmp_path,
    copias=1,
    desplazamiento=(40.0, 0.0),
    alinear=True,
    a_todas=False,
    **variante,
):
    """Las copias van como inserciones del bloque ``NOTAS``; la última (o todas, con
    ``a_todas``) lleva la ``variante``."""
    doc = ezdxf.new("R2010")
    _bloque(doc, "NOTAS", alinear)
    if variante:
        _bloque(doc, "NOTAS_VARIANTE", alinear, **variante)
    msp = doc.modelspace()
    for i in range(copias):
        con_variante = variante and (a_todas or i == copias - 1)
        msp.add_blockref(
            "NOTAS_VARIANTE" if con_variante else "NOTAS",
            (desplazamiento[0] * i, desplazamiento[1] * i),
        )
    ruta = tmp_path / "tabla.dxf"
    doc.saveas(ruta)
    return DxfParser().parse_file(ruta).entities


def _textos(entidades):
    return [e for e in entidades if e.is_textual]


def _hoja_del_archivo(e):
    return e.source_file


def _por_columna(e):
    """Dos hojas: lo que cae a la izquierda de x=20 es ES-100 y lo demás ES-200."""
    return "ES-100" if ancla_texto(e)[0] < 20 else "ES-200"


def _tablas(tmp_path, copias=1, hoja_de=_hoja_del_archivo, lector="varillas", **kw):
    """Las tablas con el lector de varillas, o con el general (que deja ``No.`` como renglón)."""
    textos = _textos(_entidades(tmp_path, copias=copias, **kw))
    if lector == "varillas":
        return leer_tablas_de_varillas(textos, hoja_de)
    return leer_tablas(textos, ENCABEZADOS_VARILLA, "VARILLA", hoja_de)


@pytest.mark.parametrize("lector", ["varillas", "general"])
def test_marina_table_two_copies(tmp_path, lector):
    dato, contradicciones, avisos = tabla_de_varillas(_tablas(tmp_path, copias=2, lector=lector))
    t = dato.valor
    assert dato.fuente == "cuadro" and dato.copias == 2 and contradicciones == []
    assert avisos == []
    assert sorted(t, key=float) == ["2.5", "3", "4", "5", "6", "8", "10", "12"]
    assert t["8"].model_dump() == dict(
        LA1=85, LA2=115, LT1=115, LT2=150, LG1=55, LG2=30, LG3=10, r=11
    )
    assert t["10"].LT1 is None and t["12"].LA2 == 255


@pytest.mark.parametrize("lector", ["varillas", "general"])
def test_copies_that_differ_are_reported(tmp_path, lector):
    dato, contradicciones, avisos = tabla_de_varillas(
        _tablas(tmp_path, copias=2, lector=lector, cambio={("8", "LT1"): 120})
    )
    assert contradicciones and "#8" in contradicciones[0] and "LT1" in contradicciones[0]
    assert avisos == []  # las copias que se desmienten son contradicciones, no avisos


def test_no_table_means_standard_supuesto():
    dato, contradicciones, avisos = tabla_de_varillas([])
    assert dato.fuente == "supuesto" and dato.valor["8"].LT1 is None
    assert contradicciones == [] and avisos == []


@pytest.mark.parametrize("alinear", [True, False])
@pytest.mark.parametrize("lector", ["varillas", "general"])
def test_every_value_of_the_drawing_is_read(tmp_path, alinear, lector):
    dato, contradicciones, avisos = tabla_de_varillas(
        _tablas(tmp_path, alinear=alinear, lector=lector)
    )
    # La nota de abajo, con cifras, es de la tabla pero no un valor: no se avisa de ella.
    assert contradicciones == [] and avisos == []
    assert dato.copias == 1 and dato.en_conflicto is False
    leido = {n: tuple(getattr(f, c) for c in CAMPOS) for n, f in dato.valor.items()}
    assert leido == {
        n: tuple(None if v is None else float(v) for v in vs) for n, vs in MARINA.items()
    }


def test_no_and_cm_cells_are_never_rows(tmp_path):
    """R2: sólo un número de varilla de ``NUMEROS`` es fila; ``No.`` y ``(cm)`` no lo son."""
    entidades = _textos(_entidades(tmp_path))
    texto_de = {e.entity_id: e.text for e in entidades}
    assert "No." in texto_de.values() and "(cm)" in texto_de.values()  # el plano los trae

    tablas = leer_tablas_de_varillas(entidades, _hoja_del_archivo)
    assert len(tablas) == 1
    (tabla,) = tablas
    assert [fila["VARILLA"] for fila in tabla.filas] == list(MARINA)
    assert all(fila["VARILLA"] in NUMEROS for fila in tabla.filas)
    assert "(cm)" not in {v for fila in tabla.filas for v in fila.values()}
    assert {texto_de[i] for i in tabla.entidades}.isdisjoint({"No.", "(cm)", "TABLA DE VARILLAS"})
    assert tabla.filas[0] == dict(
        zip(("VARILLA", *CAMPOS), ("2.5", *map(str, MARINA["2.5"])), strict=True)
    )

    # Leída con el lector general, las filas no se corren y ``No.`` no entra a la tabla de varillas.
    general = leer_tablas(entidades, ENCABEZADOS_VARILLA, "VARILLA", _hoja_del_archivo)
    dato, contradicciones, avisos = tabla_de_varillas(general)
    assert contradicciones == [] and avisos == [] and "No." not in dato.valor
    assert dato.valor["2.5"].LA1 == 30 and dato.valor["12"].r == 17 and len(dato.valor) == 8


def test_copies_side_by_side_and_stacked_pair_up(tmp_path):
    for desplazamiento in ((40.0, 0.0), (0.0, -10.0), (6.0, 0.0), (0.0, -3.0)):
        entidades = _textos(_entidades(tmp_path, copias=3, desplazamiento=desplazamiento))
        tablas = leer_tablas_de_varillas(entidades, _hoja_del_archivo)
        assert len(tablas) == 3
        assert all(len(t.filas) == 8 for t in tablas)
        todas = [i for t in tablas for i in t.entidades]
        assert len(todas) == len(set(todas))  # ningún texto es de dos tablas
        for leidas in (tablas, _tablas(tmp_path, copias=3, desplazamiento=desplazamiento)):
            dato, contradicciones, avisos = tabla_de_varillas(leidas)
            assert dato.copias == 3 and contradicciones == [] and len(dato.valor) == 8
            assert avisos == []


def test_each_table_keeps_its_hoja_entities_and_box(tmp_path):
    tablas = _tablas(tmp_path, copias=2, hoja_de=_por_columna)
    assert sorted(t.hoja for t in tablas) == ["ES-100", "ES-200"]
    t = next(t for t in tablas if t.hoja == "ES-200")
    assert t.encabezados == list(ENCABEZADOS_VARILLA)
    assert t.bbox[0] > 30 and t.bbox[2] < 50 and t.bbox[1] < -2 and t.bbox[3] > 0
    assert len(t.entidades) == 9 + 8 * 9 - 4  # encabezado + ocho filas, sin las cuatro celdas LT
    dato, _, _ = tabla_de_varillas(tablas)
    assert dato.copias == 2 and dato.hoja in ("ES-100", "ES-200")


def test_differing_copies_keep_both_readings(tmp_path):
    tablas = _tablas(tmp_path, copias=2, hoja_de=_por_columna, cambio={("8", "LT1"): 120})
    dato, contradicciones, avisos = tabla_de_varillas(tablas)
    assert avisos == []
    assert dato.en_conflicto and dato.copias == 1 and len(dato.alternativas) == 1
    assert len(contradicciones) == 1
    frase = contradicciones[0]
    assert "#8" in frase and "LT1" in frase and "115" in frase and "120" in frase
    assert "ES-100" in frase and "ES-200" in frase  # dice en qué hoja está cada lectura


def test_the_odd_copy_loses_to_the_other_two(tmp_path):
    dato, contradicciones, _ = tabla_de_varillas(
        _tablas(tmp_path, copias=3, cambio={("5", "r"): 8, ("8", "LT1"): 120})
    )
    assert dato.valor["5"].r == 7 and dato.valor["8"].LT1 == 115
    assert dato.copias == 2 and dato.en_conflicto
    assert len(contradicciones) == 2
    assert "#5 r" in contradicciones[0] and "#8 LT1" in contradicciones[1]


def test_a_bar_missing_in_a_copy_is_reported(tmp_path):
    dato, contradicciones, avisos = tabla_de_varillas(_tablas(tmp_path, copias=2, sin=("4",)))
    assert avisos == [] and len(contradicciones) == 1
    assert "#4" in contradicciones[0] and "falta" in contradicciones[0]


def test_an_unreadable_cell_is_empty_and_reported_never_guessed(tmp_path):
    dato, contradicciones, avisos = tabla_de_varillas(
        _tablas(tmp_path, cambio={("8", "LT1"): "1l5"})
    )
    assert dato.valor["8"].LT1 is None and dato.valor["8"].LT2 == 150
    # Una sola tabla con una celda ilegible: un aviso, y ninguna contradicción ni conflicto.
    assert contradicciones == [] and dato.en_conflicto is False
    assert len(avisos) == 1
    assert "#8" in avisos[0] and "LT1" in avisos[0] and "1l5" in avisos[0]


def test_a_unit_after_the_number_is_still_the_number(tmp_path):
    dato, contradicciones, avisos = tabla_de_varillas(
        _tablas(tmp_path, cambio={("8", "LT1"): "115 cm"})
    )
    assert dato.valor["8"].LT1 == 115 and contradicciones == [] and avisos == []


def test_tables_without_bar_rows_are_not_a_varillas_table(tmp_path):
    entidades = _textos(_entidades(tmp_path))
    solo_cabecera = [e for e in entidades if e.text in ENCABEZADOS_VARILLA or e.text == "No."]
    tablas = leer_tablas(solo_cabecera, ENCABEZADOS_VARILLA, "VARILLA", _hoja_del_archivo)
    dato, contradicciones, avisos = tabla_de_varillas(tablas)
    assert dato.fuente == "supuesto" and contradicciones == [] and avisos == []


def test_standard_table_is_the_pdf():
    esperada = {
        "2.5": (30, 30, 30, 40, 20, 10, 5, 4),
        "3": (30, 35, 35, 50, 20, 15, 5, 4),
        "4": (35, 45, 50, 65, 30, 15, 5, 6),
        "5": (40, 60, 60, 80, 35, 20, 10, 7),
        "6": (50, 70, 70, 100, 40, 25, 10, 9),
        "8": (85, 115, None, None, 55, 30, 10, 11),
        "10": (130, 180, None, None, 65, 40, 15, 14),
        "12": (185, 255, None, None, 80, 50, 15, 17),
    }
    assert list(TABLA_ESTANDAR) == list(esperada)
    for numero, valores in esperada.items():
        assert tuple(getattr(TABLA_ESTANDAR[numero], c) for c in CAMPOS) == valores
    assert isinstance(TABLA_ESTANDAR["3"], FilaVarilla)


def test_standard_supuesto_is_a_copy_nobody_can_corrupt():
    dato, _, _ = tabla_de_varillas([])
    dato.valor["8"].LT1 = 999
    dato.valor["99"] = FilaVarilla()
    assert TABLA_ESTANDAR["8"].LT1 is None and "99" not in TABLA_ESTANDAR


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("2.5", "2.5"),
        ("3", "3"),
        (" 10 ", "10"),
        ("#4", "4"),
        ("2,5", "2.5"),
        ("7", "7"),
        ("No.", None),
        ("(cm)", None),
        ("", None),
        ("9", None),
        ("11", None),
        ("03", None),
        ("3/8", "3"),
        ("VAR 3", "3"),
        ("VAR. 4", "4"),
        ("VARILLA #5", "5"),
        ("var 6", "6"),
        ("No.3", "3"),
        ("NO. 4", "4"),
        ("Nº5", "5"),
        ("N°6", "6"),
        ("Ø3", "3"),
        ("%%C4", "4"),
        ('3/8"', "3"),
        ('5/16"', "2.5"),
        ('1/4"', "2"),
        ('1/2"', "4"),
        ('5/8"', "5"),
        ('3/4"', "6"),
        ('7/8"', "7"),
        ('1"', "8"),
        ('1 1/4"', "10"),
        ('1-1/2"', "12"),
        ('#3 (3/8")', "3"),
        ('3/8" (#3)', "3"),
        ('#3 = 3/8"', "3"),
        ('#3 (1/2")', None),  # dice dos varillas distintas: no se escoge
        ('3/16"', None),
        ('#3 (3/16")', None),
        ("VAR 9", None),
        ("#9", None),
        ("VAR 3/4/5", None),
        ("BARRA 3", None),
        ("TABLA No.1", None),
        ("2.50", None),
    ],
)
def test_bar_numbers_are_the_ones_in_numeros(texto, esperado):
    assert numero_de_varilla(texto) == esperado


# --- lo que no entra en ninguna celda se avisa, nunca se pierde ------------------------------


def _y_de(numero, hueco=0.0, paso=PASO):
    """La ``y`` de la fila de una varilla en el bloque de prueba."""
    return -paso - paso * (list(MARINA).index(numero) + 1) - hueco


def _leidas(tmp_path, **kw):
    """El dato, las contradicciones y los avisos con los dos lectores: deben coincidir."""
    por_lector = {
        lector: tabla_de_varillas(_tablas(tmp_path, lector=lector, **kw))
        for lector in ("varillas", "general")
    }
    assert por_lector["varillas"][0].valor == por_lector["general"][0].valor
    assert por_lector["varillas"][2] == por_lector["general"][2]
    return por_lector["varillas"]


def test_a_blank_row_in_the_middle_does_not_swallow_the_rest_silently(tmp_path):
    # Tres renglones en blanco antes de #5: el hueco (1.0) pasa de 2.5 pasos (0.625).
    dato, contradicciones, avisos = _leidas(tmp_path, hueco_antes=("5", 3))
    assert list(dato.valor) == ["2.5", "3", "4"]  # lo de antes del hueco sí se lee
    assert contradicciones == []
    (aviso,) = avisos
    assert "después de un hueco" in aviso
    assert "«5»" in aviso and "«6»" in aviso and "«12»" in aviso  # dice qué quedó fuera

    (tabla,) = _tablas(tmp_path, hueco_antes=("5", 3), lector="varillas")
    # Cada texto con cifras después del hueco está anotado: 5 números de varilla y sus celdas.
    assert len(tabla.sin_celda) == 5 + 3 * 8 + 2 * 6
    assert {s.motivo for s in tabla.sin_celda} == {"tras_un_hueco"}
    assert "30 cm" not in " ".join(s.texto for s in tabla.sin_celda)  # la nota de abajo no cuenta


def test_hueco_maximo_decides_how_far_the_table_goes(tmp_path):
    entidades = _textos(_entidades(tmp_path, hueco_antes=("5", 3)))
    sola = leer_tablas_de_varillas(entidades, _hoja_del_archivo)
    todo = leer_tablas(
        entidades,
        ENCABEZADOS_VARILLA,
        "VARILLA",
        _hoja_del_archivo,
        fila_valida=lambda t: numero_de_varilla(t) is not None,
        hueco_maximo=5.0,
    )
    assert [len(t.filas) for t in sola] == [3] and [len(t.filas) for t in todo] == [8]
    por_varillas = leer_tablas_de_varillas(entidades, _hoja_del_archivo, hueco_maximo=5.0)
    assert [len(t.filas) for t in por_varillas] == [8]
    assert todo[0].sin_celda == []


def test_a_value_between_two_columns_is_reported_not_dropped(tmp_path):
    # El 85 de #8 queda entre VARILLA y LA1: a más de media separación de las dos.
    dato, contradicciones, avisos = _leidas(tmp_path, desfase={("8", "LA1"): (-0.49, 0.0)})
    assert dato.valor["8"].LA1 is None and dato.valor["8"].LA2 == 115
    assert contradicciones == []
    (aviso,) = avisos
    assert "«85»" in aviso and "ninguna columna" in aviso and "#8" in aviso


def test_a_value_shifted_up_is_reported_and_nobody_is_blamed(tmp_path):
    # El 6 de la r de #4 sube 0.15: a 0.10 de la línea de #3 y a 0.15 de la suya.
    dato, contradicciones, avisos = _leidas(tmp_path, desfase={("4", "r"): (0.0, 0.15)})
    assert dato.valor["3"].r == 4  # #3 conserva lo suyo, no se le pega el 6
    assert dato.valor["4"].r is None and dato.valor["4"].LA1 == 35
    assert contradicciones == []
    (aviso,) = avisos
    assert "«6»" in aviso and "columna r" in aviso and "#3" in aviso
    assert "dice" not in aviso  # no acusa a la celda de #3 de decir algo ilegible


def test_two_texts_on_one_cell_are_reported_not_picked(tmp_path):
    # El 11 de la r de #8 baja 0.20: cae sobre la línea de #10, que ya tiene su 14.
    dato, contradicciones, avisos = _leidas(tmp_path, desfase={("8", "r"): (0.0, -0.20)})
    assert dato.valor["8"].r is None and dato.valor["10"].r is None  # no se escoge ninguno
    assert contradicciones == []
    (aviso,) = avisos
    assert "#10" in aviso and "r" in aviso and "«11 14»" in aviso


@pytest.mark.parametrize("falsa", ["9", "2.50"])
def test_a_row_that_looks_like_a_bar_but_is_not_in_numeros_is_reported(tmp_path, falsa):
    y = _y_de("12") - PASO
    extra = [(falsa, X_ENCABEZADO["VARILLA"], y), ("33", X_ENCABEZADO["LA1"], y)]
    dato, contradicciones, avisos = _leidas(tmp_path, nota=False, extra=extra)
    assert falsa not in dato.valor and len(dato.valor) == 8  # R2: no es fila
    assert contradicciones == []
    (aviso,) = avisos
    assert f"«{falsa}»" in aviso and "no es un número de varilla" in aviso  # y no se calla


def test_texts_with_digits_below_the_table_are_not_its_business(tmp_path):
    extra = [("33", X_ENCABEZADO["LA1"], _y_de("12") - 0.6), ("A-1", -1.65, _y_de("12") - 1.5)]
    # El lector de varillas sabe qué es un renglón de la tabla; uno general no lo puede saber.
    _, _, avisos = tabla_de_varillas(_tablas(tmp_path, extra=extra, lector="varillas"))
    assert avisos == []


def test_the_same_aviso_in_every_copy_is_said_once_with_the_count(tmp_path):
    dato, contradicciones, avisos = tabla_de_varillas(
        _tablas(tmp_path, copias=3, a_todas=True, cambio={("8", "LT1"): "1l5"})
    )
    assert dato.copias == 3 and contradicciones == []
    (aviso,) = avisos
    assert "en 3 copias" in aviso and "#8" in aviso and "LT1" in aviso and "1l5" in aviso


def test_the_avisos_of_different_copies_stay_apart(tmp_path):
    dato, contradicciones, avisos = tabla_de_varillas(
        _tablas(tmp_path, copias=2, hoja_de=_por_columna, cambio={("8", "LT1"): "1l5"})
    )
    (aviso,) = avisos
    assert "ES-200" in aviso and "en 2 copias" not in aviso  # sólo la copia que lo trae
    assert len(contradicciones) == 1 and "#8 LT1" in contradicciones[0]  # y además difieren


def test_a_value_out_of_range_is_not_used_and_is_reported(tmp_path):
    dato, contradicciones, avisos = _leidas(
        tmp_path, cambio={("8", "LT1"): 450, ("8", "LT2"): 0, ("6", "LA1"): 400}
    )
    assert dato.valor["8"].LT1 is None and dato.valor["8"].LT2 is None
    assert dato.valor["6"].LA1 == 400  # el límite es de 1 a 400 cm, ambos incluidos
    assert contradicciones == [] and len(avisos) == 2
    assert "#8" in avisos[0] and "LT1" in avisos[0] and "450" in avisos[0]
    assert "#8" in avisos[1] and "LT2" in avisos[1]


# --- cómo se escribe el número de varilla ------------------------------------------------------

_FORMAS_DE_ESCRIBIR = {
    "VAR": "VAR {}",
    "VAR.": "VAR. {}",
    "VARILLA": "VARILLA {}",
    "No.": "No.{}",
    "NO.": "NO. {}",
    "Nº": "Nº{}",
    "Ø": "Ø{}",
    "%%C": "%%C{}",
    "#": "#{}",
}
_PULGADAS_DE_CADA_UNA = {
    "2.5": '5/16"',
    "3": '3/8"',
    "4": '1/2"',
    "5": '5/8"',
    "6": '3/4"',
    "8": '1"',
    "10": '1 1/4"',
    "12": '1 1/2"',
}


def _esperado_de_marina():
    return {n: tuple(None if v is None else float(v) for v in vs) for n, vs in MARINA.items()}


def _como_tuplas(dato):
    return {n: tuple(getattr(f, c) for c in CAMPOS) for n, f in dato.valor.items()}


@pytest.mark.parametrize("forma", list(_FORMAS_DE_ESCRIBIR))
def test_every_common_labelling_of_a_bar_number_is_read(tmp_path, forma):
    etiquetas = {n: _FORMAS_DE_ESCRIBIR[forma].format(n) for n in MARINA}
    dato, contradicciones, avisos = _leidas(tmp_path, etiquetas=etiquetas)
    assert dato.fuente == "cuadro" and _como_tuplas(dato) == _esperado_de_marina()
    assert contradicciones == [] and avisos == []


def test_bars_written_as_inch_fractions_are_read_as_their_mexican_number(tmp_path):
    dato, contradicciones, avisos = _leidas(tmp_path, etiquetas=_PULGADAS_DE_CADA_UNA)
    assert dato.fuente == "cuadro" and _como_tuplas(dato) == _esperado_de_marina()
    assert contradicciones == [] and avisos == []


def test_a_label_that_gives_both_forms_is_read_when_they_agree(tmp_path):
    etiquetas = {"3": '#3 (3/8")', "4": "#4", "5": "#5"}
    dato, _, avisos = _leidas(tmp_path, etiquetas=etiquetas)
    assert _como_tuplas(dato) == _esperado_de_marina() and avisos == []


def test_a_label_that_disagrees_with_itself_is_reported_not_guessed(tmp_path):
    dato, contradicciones, avisos = _leidas(tmp_path, etiquetas={"3": '#3 (1/2")'})
    assert "3" not in dato.valor and len(dato.valor) == 7
    assert contradicciones == []
    (aviso,) = avisos
    assert '«#3 (1/2")»' in aviso and "#3 y #4" in aviso and "no se lee" in aviso


@pytest.mark.parametrize("etiqueta", ["VAR 9", "#9", "2.50", '3/16"', "BARRA 6", "VAR 3/4/5"])
def test_a_label_with_digits_that_is_not_a_bar_is_reported_mid_table(tmp_path, etiqueta):
    dato, contradicciones, avisos = _leidas(tmp_path, etiquetas={"6": etiqueta})
    assert "6" not in dato.valor and len(dato.valor) == 7  # el resto de la tabla sí se lee
    assert contradicciones == []
    (aviso,) = avisos
    assert f"«{etiqueta}»" in aviso and "no es un número de varilla" in aviso


def test_a_table_whose_labels_none_is_a_bar_falls_back_to_the_standard_with_avisos(tmp_path):
    etiquetas = {n: f"BARRA {n}" for n in MARINA}
    dato, contradicciones, avisos = _leidas(tmp_path, etiquetas=etiquetas)
    assert dato.fuente == "supuesto" and contradicciones == []
    assert len(avisos) == 8 and all("no es un número de varilla" in a for a in avisos)


def test_a_label_with_digits_at_the_first_row_is_not_lost(tmp_path):
    dato, _, avisos = _leidas(tmp_path, etiquetas={"2.5": "VAR 9"})
    assert "2.5" not in dato.valor and len(dato.valor) == 7
    assert len(avisos) == 1 and "«VAR 9»" in avisos[0]


# --- celdas que no están a la altura del número, y tablas con otro paso -------------------------


def _como_en_marina(dato, contradicciones, avisos):
    assert dato.fuente == "cuadro" and _como_tuplas(dato) == _esperado_de_marina()
    assert contradicciones == [] and avisos == []


def test_values_centred_on_a_bar_number_written_at_its_baseline_are_read(tmp_path):
    # Los números en la esquina inferior izquierda; los valores centrados, media altura arriba.
    _como_en_marina(*_leidas(tmp_path, numeros_en_la_base=True))


def test_values_taller_than_the_bar_numbers_are_read(tmp_path):
    # Valores 1.5 veces más altos y centrados: su centro queda 0.09 arriba de la base.
    _como_en_marina(*_leidas(tmp_path, numeros_en_la_base=True, alto_valores=0.18))


def test_values_a_little_off_the_line_of_a_tall_pitch_are_read(tmp_path):
    # 0.07 arriba con un paso de 0.28: dentro de 0.3 pasos (0.084), lejos de la fila vecina.
    _como_en_marina(*_leidas(tmp_path, paso=0.28, desfase_valores=0.07))


def test_a_header_with_smaller_text_than_the_body_is_read(tmp_path):
    _como_en_marina(*_leidas(tmp_path, alto_encabezado=0.06, alto_valores=0.12, alto_numeros=0.12))


def test_a_pitch_of_three_heights_is_read(tmp_path):
    _como_en_marina(*_leidas(tmp_path, paso=0.36))


def test_values_midway_between_two_rows_are_reported_and_the_table_is_not_used(tmp_path):
    # Todos los valores a medio camino entre dos filas: ninguno cae sobre una línea.
    dato, contradicciones, avisos = _leidas(tmp_path, desfase_valores=0.125)
    assert dato.fuente == "supuesto" and contradicciones == []  # no tapa a la estándar con nada
    assert any("ninguna celda de valores" in a for a in avisos)
    assert any("no está sobre la línea" in a for a in avisos)  # y dice qué textos no cayeron


def test_a_bar_row_without_a_single_value_is_not_kept_as_a_cuadro_row(tmp_path):
    vacia = {("5", c): None for c in CAMPOS}
    dato, contradicciones, avisos = _leidas(tmp_path, cambio=vacia)
    assert "5" not in dato.valor and len(dato.valor) == 7 and dato.fuente == "cuadro"
    assert contradicciones == []
    (aviso,) = avisos
    assert "#5" in aviso and "ningún valor" in aviso


def test_a_blank_gap_beyond_the_old_window_is_still_scanned(tmp_path):
    # Seis renglones en blanco: 1.75 de hueco, más de 3 × 2.5 alturas, menos de 10 pasos.
    dato, contradicciones, avisos = _leidas(tmp_path, hueco_antes=("5", 6))
    assert list(dato.valor) == ["2.5", "3", "4"] and contradicciones == []
    (aviso,) = avisos
    for varilla in ("5", "6", "8", "10", "12"):
        assert f"«{varilla}»" in aviso  # se nombran todos los renglones que no se leen


def test_every_lost_row_is_named_when_the_pitch_is_tall(tmp_path):
    dato, _, avisos = _leidas(tmp_path, paso=0.36, hueco_antes=("5", 3))
    assert list(dato.valor) == ["2.5", "3", "4"]
    (aviso,) = avisos
    assert all(f"«{v}»" in aviso for v in ("5", "6", "8", "10", "12"))


def test_a_single_blank_row_no_longer_cuts_the_table(tmp_path):
    # Un renglón en blanco (2 pasos de hueco) cabe en 2.5 pasos: se lee todo.
    dato, contradicciones, avisos = _leidas(tmp_path, hueco_antes=("5", 1))
    assert _como_tuplas(dato) == _esperado_de_marina()
    assert contradicciones == [] and avisos == []


# --- el renglón de encabezados --------------------------------------------------------------


def test_a_stray_token_on_the_header_baseline_cannot_null_a_column(tmp_path):
    # Una «r» suelta en x=1.0 y una «LA1» suelta a la izquierda del ancla.
    extra = [("r", 1.0, 0.0), ("LA1", -2.2, 0.0)]
    dato, contradicciones, avisos = _leidas(tmp_path, extra=extra)
    assert dato.fuente == "cuadro" and dato.valor["8"].r == 11 and dato.valor["8"].LA1 == 85
    assert all(f.r is not None and f.LA1 is not None for f in dato.valor.values())
    assert contradicciones == [] and avisos == []


def test_a_header_token_that_appears_twice_between_its_neighbours_is_reported(tmp_path):
    dato, contradicciones, avisos = tabla_de_varillas(
        _tablas(tmp_path, extra=[("LA1", -1.2, 0.0)], lector="varillas")
    )
    assert dato.fuente == "supuesto" and contradicciones == []  # no se adivina cuál es
    (aviso,) = avisos
    assert "ambiguo" in aviso and "LA1" in aviso and "VARILLA" in aviso


def test_a_header_without_a_token_is_rejected_with_its_aviso(tmp_path):
    tablas = _tablas(tmp_path, sin_encabezado=("LA2",), lector="varillas")
    (rechazada,) = tablas
    assert rechazada.filas == [] and "LA2" in rechazada.avisos[0]
    dato, _, avisos = tabla_de_varillas(tablas)
    assert dato.fuente == "supuesto"  # el plano trae la tabla, pero no se pudo leer: se dice
    assert len(avisos) == 1 and "LA2" in avisos[0]


def test_a_header_out_of_order_is_rejected_with_its_aviso(tmp_path):
    # Sin la LA2 de su lugar y con una LA2 a la izquierda de todo: no hay orden posible.
    extra = [("LA2", -3.0, 0.0)]
    tablas = _tablas(tmp_path, sin_encabezado=("LA2",), extra=extra, lector="varillas")
    (rechazada,) = tablas
    assert rechazada.filas == [] and "LA2" in rechazada.avisos[0]


def test_a_damaged_header_does_not_steal_the_tokens_of_the_copy_next_to_it(tmp_path):
    # La copia dañada (sin LA2) queda a la izquierda: sin cuidado tomaría la LA2 de la otra.
    entidades = _textos(
        _entidades(tmp_path, copias=2, desplazamiento=(-40.0, 0.0), sin_encabezado=("LA2",))
    )
    tablas = leer_tablas_de_varillas(entidades, _hoja_del_archivo)
    rechazada, buena = tablas  # de izquierda a derecha
    assert rechazada.filas == [] and "no hay «LA2»" in rechazada.avisos[0]  # y no "ambiguo"
    assert len(buena.filas) == 8
    dato, contradicciones, avisos = tabla_de_varillas(tablas)
    assert dato.fuente == "cuadro" and dato.copias == 1 and contradicciones == []
    assert len(avisos) == 1 and "LA2" in avisos[0]
    assert dato.valor["8"].LT1 == 115 and dato.valor["8"].r == 11


def test_a_stray_last_token_between_the_last_two_is_reported(tmp_path):
    # Una «r» suelta entre LG3 y la r de verdad: sin la regla, la r de verdad quedaba fuera.
    dato, contradicciones, avisos = tabla_de_varillas(
        _tablas(tmp_path, extra=[("r", 3.5, 0.0)], lector="varillas")
    )
    assert dato.fuente == "supuesto" and contradicciones == []
    (aviso,) = avisos
    assert "ambiguo" in aviso and "«r»" in aviso and "LG3" in aviso


def test_a_stray_last_token_far_to_the_right_is_not_this_tables_header(tmp_path):
    dato, _, avisos = tabla_de_varillas(
        _tablas(tmp_path, extra=[("r", 9.0, 0.0)], lector="varillas")
    )
    assert dato.fuente == "cuadro" and dato.valor["8"].r == 11 and avisos == []


def test_digits_in_a_column_the_header_does_not_name_are_reported(tmp_path):
    # Un texto a la derecha de la última columna, en la línea de #8 y a menos de tres separaciones.
    extra = [("123", 5.0, _y_de("8"))]
    dato, contradicciones, avisos = tabla_de_varillas(
        _tablas(tmp_path, extra=extra, lector="varillas")
    )
    assert dato.fuente == "cuadro" and dato.valor["8"].r == 11 and contradicciones == []
    (aviso,) = avisos
    assert "«123»" in aviso and "ninguna columna" in aviso and "#8" in aviso


def test_the_next_copys_texts_are_not_a_column_the_header_does_not_name(tmp_path):
    entidades = _textos(_entidades(tmp_path, copias=2, desplazamiento=(6.0, 0.0)))
    tablas = leer_tablas_de_varillas(entidades, _hoja_del_archivo)
    assert [t.sin_celda for t in tablas] == [[], []]


def test_side_by_side_tables_are_not_swapped_by_float_noise_in_y(tmp_path):
    entidades = _textos(_entidades(tmp_path, copias=3, desplazamiento=(40.0, 1e-9)))
    tablas = leer_tablas_de_varillas(entidades, _hoja_del_archivo)
    assert [round(t.bbox[0]) for t in tablas] == [-2, 38, 78]  # de izquierda a derecha
    assert all(len(t.filas) == 8 for t in tablas)
    entidades = _textos(_entidades(tmp_path, copias=3, desplazamiento=(40.0, -1e-9)))
    tablas = leer_tablas_de_varillas(entidades, _hoja_del_archivo)
    assert [round(t.bbox[0]) for t in tablas] == [-2, 38, 78]


def test_headers_match_without_accents_or_case(tmp_path):
    def build(msp):
        for x, t in zip((0, 3, 6), ("MARCA", "SECCIÓN", "Armado"), strict=True):
            _suelto(msp, t, x, 10)
        _suelto(msp, "K-1", 0, 9.5)
        _suelto(msp, "15x20", 3, 9.5)

    (tabla,) = _general(tmp_path, build)  # pide «SECCION» y «ARMADO»
    assert tabla.filas == [{"MARCA": "K-1", "SECCION": "15x20"}]
    (otra,) = _general(tmp_path, build, encabezados=("MARCA", "SECCIÓN", "ARMADO"))
    assert otra.filas == [{"MARCA": "K-1", "SECCIÓN": "15x20"}]


# --- el lector general ---------------------------------------------------------------------


def _general(tmp_path, build, ancla="MARCA", encabezados=("MARCA", "SECCION", "ARMADO"), **kw):
    doc = ezdxf.new("R2010")
    build(doc.modelspace())
    ruta = tmp_path / "general.dxf"
    doc.saveas(ruta)
    entidades = DxfParser().parse_file(ruta).entities
    return leer_tablas(_textos(entidades), encabezados, ancla, _hoja_del_archivo, **kw)


def _suelto(msp, texto, x, y, alto=0.25):
    msp.add_text(texto, height=alto).set_placement((x, y))


def test_a_generic_table_leaves_empty_cells_absent(tmp_path):
    def build(msp):
        for x, t in zip((0, 3, 6), ("MARCA", "SECCION", "ARMADO"), strict=True):
            _suelto(msp, t, x, 10)
        _suelto(msp, "K-1", 0, 9.5)
        _suelto(msp, "15x20", 3, 9.5)
        _suelto(msp, "4#3", 6, 9.5)
        _suelto(msp, "K-2", 0, 9.0)  # sin sección
        _suelto(msp, "6#4", 6, 9.0)
        _suelto(msp, "K-3", 0, 8.5)
        _suelto(msp, "TEXTO LEJOS", 20, 9.0)  # fuera de toda columna
        _suelto(msp, "OTRA COSA", 0, 5.0)  # muy abajo: la tabla ya terminó

    (tabla,) = _general(tmp_path, build)
    assert tabla.encabezados == ["MARCA", "SECCION", "ARMADO"]
    assert tabla.filas == [
        {"MARCA": "K-1", "SECCION": "15x20", "ARMADO": "4#3"},
        {"MARCA": "K-2", "ARMADO": "6#4"},
        {"MARCA": "K-3"},
    ]
    assert len(tabla.entidades) == 3 + 3 + 3  # encabezado, marcas y celdas con texto
    assert tabla.bbox[0] == 0 and tabla.bbox[3] == pytest.approx(10.25)


def test_a_far_row_ends_the_table(tmp_path):
    def build(msp):
        for x, t in zip((0, 3, 6), ("MARCA", "SECCION", "ARMADO"), strict=True):
            _suelto(msp, t, x, 10)
        _suelto(msp, "K-1", 0, 9.5)
        _suelto(msp, "15x20", 3, 9.5)
        _suelto(msp, "K-9", 0, 8.0)  # 1.5 de hueco con filas de 0.25: ya no es de la tabla
        _suelto(msp, "30x30", 3, 8.0)

    (tabla,) = _general(tmp_path, build)
    assert tabla.filas == [{"MARCA": "K-1", "SECCION": "15x20"}]
    # Lo que sigue después del hueco no se lee pero tampoco se pierde.
    assert [(s.texto, s.motivo) for s in tabla.sin_celda] == [
        ("K-9", "tras_un_hueco"),
        ("30x30", "tras_un_hueco"),
    ]


def test_the_header_needs_every_token_on_one_baseline(tmp_path):
    def sin_un_token(msp):
        _suelto(msp, "MARCA", 0, 10)
        _suelto(msp, "SECCION", 3, 10)
        _suelto(msp, "K-1", 0, 9.5)

    def en_otra_linea(msp):
        _suelto(msp, "MARCA", 0, 10)
        _suelto(msp, "SECCION", 3, 10)
        _suelto(msp, "ARMADO", 6, 9.0)  # otro renglón
        _suelto(msp, "K-1", 0, 9.5)

    for build in (sin_un_token, en_otra_linea):
        (rechazada,) = _general(tmp_path, build)  # empezó el renglón: se avisa, no se calla
        assert rechazada.filas == [] and len(rechazada.avisos) == 1
        assert "ARMADO" in rechazada.avisos[0]

    def sin_ancla_en_la_linea(msp):
        _suelto(msp, "MARCA", 0, 10)  # una palabra suelta, no un renglón de encabezados
        _suelto(msp, "K-1", 0, 9.5)

    assert _general(tmp_path, sin_ancla_en_la_linea) == []


def test_the_header_cannot_straddle_two_hojas(tmp_path):
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for x, t in zip((0, 3, 6), ("MARCA", "SECCION", "ARMADO"), strict=True):
        _suelto(msp, t, x, 10)
    _suelto(msp, "K-1", 0, 9.5)
    ruta = tmp_path / "dos_hojas.dxf"
    doc.saveas(ruta)
    textos = _textos(DxfParser().parse_file(ruta).entities)

    def por_x(e):
        return "A" if ancla_texto(e)[0] < 5 else "B"

    (partida,) = leer_tablas(textos, ("MARCA", "SECCION", "ARMADO"), "MARCA", por_x)
    assert partida.filas == [] and "ARMADO" in partida.avisos[0]  # ARMADO está en la hoja B
    (tabla,) = leer_tablas(textos, ("MARCA", "SECCION", "ARMADO"), "MARCA", _hoja_del_archivo)
    assert tabla.filas == [{"MARCA": "K-1"}]


def test_a_row_filter_drops_the_cells_of_the_rows_it_drops(tmp_path):
    """``fila_valida`` descarta filas, y sus celdas no se pasan a la fila de al lado."""

    def build(msp):
        for x, t in zip((0, 3, 6), ("MARCA", "SECCION", "ARMADO"), strict=True):
            _suelto(msp, t, x, 10)
        _suelto(msp, "No.", 0, 9.75)
        _suelto(msp, "(cm)", 3, 9.7)  # en la fila de ``No.``, sobre la columna de «15x20»
        _suelto(msp, "K-1", 0, 9.5)
        _suelto(msp, "15x20", 3, 9.5)

    (tabla,) = _general(tmp_path, build, fila_valida=lambda t: t.startswith("K-"))
    assert tabla.filas == [{"MARCA": "K-1", "SECCION": "15x20"}]


def test_a_table_stops_where_the_next_copys_header_begins(tmp_path):
    def build(msp):
        for y0, marcas in ((10.0, ("K-1", "K-2")), (8.5, ("K-5", "K-6"))):
            for x, t in zip((0, 3, 6), ("MARCA", "SECCION", "ARMADO"), strict=True):
                _suelto(msp, t, x, y0)
            for i, marca in enumerate(marcas, start=1):
                _suelto(msp, marca, 0, y0 - 0.5 * i)
                _suelto(msp, f"{marca}-sec", 3, y0 - 0.5 * i)

    primera, segunda = _general(tmp_path, build)
    assert [f["MARCA"] for f in primera.filas] == ["K-1", "K-2"]
    assert [f["MARCA"] for f in segunda.filas] == ["K-5", "K-6"]
    assert [f["SECCION"] for f in segunda.filas] == ["K-5-sec", "K-6-sec"]


# --- R33: lo que cuelga después de un hueco y la etiqueta larga del último renglón ---------------

_COLA_SIN_VARILLAS = {"5": "9", "6": "11", "8": "VAR 9", "10": "#9", "12": "2.50"}


def test_a_tail_of_only_non_bar_rows_after_a_gap_is_reported_by_both_readers(tmp_path):
    # Tres renglones en blanco y luego cinco renglones con cifras que no son varillas de NUMEROS.
    dato, contradicciones, avisos = _leidas(
        tmp_path, hueco_antes=("5", 3), etiquetas=_COLA_SIN_VARILLAS
    )
    assert list(dato.valor) == ["2.5", "3", "4"] and contradicciones == []
    (aviso,) = avisos
    assert "después de un hueco" in aviso
    for etiqueta in _COLA_SIN_VARILLAS.values():
        assert f"«{etiqueta}»" in aviso  # dice cada renglón que no se lee


def test_the_tail_of_non_bar_rows_leaves_the_same_traces_in_both_readers(tmp_path):
    por_lector = {
        lector: _tablas(
            tmp_path, hueco_antes=("5", 3), etiquetas=_COLA_SIN_VARILLAS, nota=False, lector=lector
        )
        for lector in ("varillas", "general")
    }
    for tablas in por_lector.values():
        (tabla,) = tablas
        assert {s.motivo for s in tabla.sin_celda} == {"tras_un_hueco"}
    visto = {
        lector: sorted((s.texto, s.motivo) for s in tablas[0].sin_celda)
        for lector, tablas in por_lector.items()
    }
    assert visto["varillas"] == visto["general"]
    assert len(visto["varillas"]) == 5 + 3 * 8 + 2 * 6  # los cinco renglones y todas sus celdas


@pytest.mark.parametrize("etiqueta", ["9", "11", "VAR 9", "#9", "2.50", '3/16"'])
def test_a_lone_number_like_label_after_a_gap_is_reported_with_no_values_at_all(tmp_path, etiqueta):
    y = _y_de("12") - 4 * PASO  # 4 pasos más abajo: pasa de los 2.5 pasos del hueco
    extra = [(etiqueta, X_ENCABEZADO["VARILLA"], y)]
    dato, contradicciones, avisos = _leidas(tmp_path, nota=False, extra=extra)
    assert len(dato.valor) == 8 and contradicciones == []
    (aviso,) = avisos
    assert "después de un hueco" in aviso and f"«{etiqueta}»" in aviso


def test_a_label_that_is_not_number_like_after_a_gap_is_reported_when_values_sit_on_its_line(
    tmp_path,
):
    etiquetas = {n: f"BARRA {n}" for n in ("5", "6", "8", "10", "12")}
    dato, contradicciones, avisos = _leidas(tmp_path, hueco_antes=("5", 3), etiquetas=etiquetas)
    assert list(dato.valor) == ["2.5", "3", "4"] and contradicciones == []
    (aviso,) = avisos
    assert "después de un hueco" in aviso and "«BARRA 5»" in aviso and "«BARRA 12»" in aviso


def test_an_unrelated_label_after_a_gap_with_nothing_on_its_line_stays_silent(tmp_path):
    y = _y_de("12") - 4 * PASO
    extra = [("A-1", X_ENCABEZADO["VARILLA"], y), ("PLANTA 2", X_ENCABEZADO["VARILLA"], y - PASO)]
    _, _, avisos = tabla_de_varillas(_tablas(tmp_path, nota=False, extra=extra, lector="varillas"))
    assert avisos == []


_ETIQUETA_LARGA = "VARILLA CORRUGADA DEL No. 5 (5/8 PULG)"


def test_a_long_label_with_digits_in_the_last_row_is_reported_with_its_cells(tmp_path):
    dato, contradicciones, avisos = _leidas(tmp_path, etiquetas={"12": _ETIQUETA_LARGA})
    assert "12" not in dato.valor and len(dato.valor) == 7  # lo demás de la tabla sí se lee
    assert contradicciones == []
    (aviso,) = avisos
    assert f"«{_ETIQUETA_LARGA}»" in aviso and "no es un número de varilla" in aviso


def test_a_label_without_digits_but_with_values_on_its_line_is_reported(tmp_path):
    dato, contradicciones, avisos = _leidas(tmp_path, etiquetas={"12": "VARILLA CORRUGADA"})
    assert "12" not in dato.valor and len(dato.valor) == 7 and contradicciones == []
    (aviso,) = avisos
    assert "«VARILLA CORRUGADA»" in aviso and "no es un número de varilla" in aviso


def test_a_label_without_digits_and_without_values_is_not_a_row_and_stays_silent(tmp_path):
    # Como la leyenda de Marina: texto largo bajo la tabla con cifras pero nada en su línea.
    y = _y_de("12") - 0.5 * PASO
    extra = [("LA1=LONGITUD DE ANCLAJE PARA VARILLAS CON MENOS DE 30 cm", -1.65, y)]
    _, _, avisos = tabla_de_varillas(_tablas(tmp_path, nota=False, extra=extra, lector="varillas"))
    assert avisos == []


# --- notas numeradas -----------------------------------------------------------------------------

MARINA_GENERALES = [
    "4. EL RECUBRIMIENTO MINIMO LIBRE, NO SERA MENOR QUE EL DIAMETRO DEL",
    "REFUERZO LONGITUDINAL NI MENOR A:",
    "5.0 CM EN ELEMENTOS ESTRUCTURALES DE CIMENTACION",
    "5.0 CM EN COLUMNAS, EN CASO DE USAR PAQUETES DE VARILLAS SERA 1.5",
    "VECES EL DIAMETRO DE LA BARRA MAS GRUESA.",
    "4.0 CM EN TRABES Y LOSAS",
    "3.0 A 5.0 CM EN CASTILLOS, CADENAS, DALAS Y CERRAMIENTOS",
    "5. EN TODOS LOS ELEMENTOS DE CONCRETO EL CURADO DEBERA MANTENERSE",
]
MARINA_REFUERZO = [
    "3. EN TRABES LA SEPARACION DE LOS ESTRIBOS EMPEZARÁ A PARTIR DEL PAÑO",
    "DE LOS APOYOS COLOCANDO EL PRIMER ESTRIBO A 6 CMS.",
    "4. NO SE PERMITIRA TRASLAPAR NI SOLDAR MAS DEL 50%%% DEL REFUERZO",
    "EN UNA MISMA SECCION, UNICAMENTE SE PERMITIRA TRASLAPAR VARILLA",
    "HASTA EL #6, DEL #8 Y DIAMETROS MAYORES SE SOLDARAN",
    "COMO LO INDICA LA FIG-D.",
    "7. EL ANCLAJE DE ESTRIBOS Y GRAPAS SE HARA CON UN DOBLEZ A 135° Y 180°",
    "RESPECTIVAMENTE, RESPETANDO LOS RADIOS (r) INDICADOS EN LA TABLA DE",
    "VARILLAS, SEGUIDO DE UN TRAMO RECTO DE 10Ø COMO SE INDICA EN LA",
    "FIG-B.",
]


def _hoja_por_bloque(e):
    """Una hoja por cada 100 unidades en x (los bloques de prueba van separados así)."""
    return f"ES-{int(ancla_texto(e)[0] // 100) + 1:03d}"


def _escribir_notas(msp, grupos, x=0.0, y0=0.0, paso=0.22, alto=0.10, alto_titulo=0.14):
    """Los grupos (título o ``None``, renglones) como TEXT alineados a la izquierda; un renglón
    puede ser ``(texto, dx)`` para ponerlo con sangría. Devuelve la ``y`` de la base."""
    y = y0
    for titulo, renglones in grupos:
        if titulo is not None:
            msp.add_text(titulo, height=alto_titulo).set_placement((x + 0.4, y))
            y -= paso * 1.2
        for r in renglones:
            texto, dx = (r, 0.0) if isinstance(r, str) else r
            msp.add_text(texto, height=alto).set_placement((x + dx, y))
            y -= paso
        y -= paso * 2  # un hueco entre grupos
    return y


def _notas_dxf(tmp_path, grupos, copias=1, separacion=100.0, **kw):
    """Los grupos como un bloque inserto ``copias`` veces, una por hoja (``_hoja_por_bloque``)."""
    doc = ezdxf.new("R2010")
    bloque = doc.blocks.new("NOTAS_PRUEBA")
    _escribir_notas(bloque, grupos, **kw)
    msp = doc.modelspace()
    for i in range(copias):
        msp.add_blockref("NOTAS_PRUEBA", (separacion * i, 0.0))
    ruta = tmp_path / "notas.dxf"
    doc.saveas(ruta)
    return DxfParser().parse_file(ruta).entities


def _lineas(tmp_path, renglones, heading, **kw):
    return _notas_dxf(tmp_path, [(heading, renglones)], **kw)


def test_notes_rejoined_by_number(tmp_path):
    entidades = _lineas(tmp_path, MARINA_REFUERZO, heading="REFUERZO :")
    notas, contradicciones = leer_notas(_textos(entidades), lambda e: "ES-001")
    assert contradicciones == []
    n4 = next(n for n in notas if n.seccion == "REFUERZO" and n.numero == 4)
    assert n4.texto.endswith("SE SOLDARAN COMO LO INDICA LA FIG-D.")
    assert n4.texto.startswith("NO SE PERMITIRA TRASLAPAR")  # sin el número
    assert [n.numero for n in notas] == [3, 4, 7]
    n7 = next(n for n in notas if n.numero == 7)
    assert n7.texto.endswith("COMO SE INDICA EN LA FIG-B.") and "135° Y 180°" in n7.texto
    assert n4.hoja == "ES-001" and n4.copias == 1 and len(n4.entidades) == 4


def test_the_percent_code_of_autocad_is_read_as_a_percent(tmp_path):
    entidades = _lineas(tmp_path, MARINA_REFUERZO, heading="REFUERZO :")
    notas, _ = leer_notas(_textos(entidades), lambda e: "ES-001")
    assert "50% DEL REFUERZO" in next(n for n in notas if n.numero == 4).texto


def test_cover_lines_that_start_with_a_number_are_not_new_notes(tmp_path):
    entidades = _lineas(tmp_path, MARINA_GENERALES, heading="NOTAS GENERALES DE ESTRUCTURA.")
    notas, _ = leer_notas(_textos(entidades), lambda e: "ES-001")
    assert [(n.seccion, n.numero) for n in notas] == [("NOTAS GENERALES DE ESTRUCTURA", 4)] + [
        ("NOTAS GENERALES DE ESTRUCTURA", 5)
    ]
    n4 = notas[0]
    # «5.0 CM EN …» y «3.0 A 5.0 CM …» son parte de la nota 4; y «REFUERZO LONGITUDINAL NI MENOR
    # A:» (mayúsculas con «:») es su continuación, no un encabezado.
    assert "NI MENOR A: 5.0 CM EN ELEMENTOS ESTRUCTURALES DE CIMENTACION 5.0 CM EN COLUMNAS" in (
        n4.texto
    )
    assert n4.texto.endswith("3.0 A 5.0 CM EN CASTILLOS, CADENAS, DALAS Y CERRAMIENTOS")
    assert "VECES EL DIAMETRO DE LA BARRA MAS GRUESA." in n4.texto


def test_a_title_right_under_a_note_is_not_part_of_the_note(tmp_path):
    """Un título más alto pegado a la última línea de la nota (a un renglón de distancia, con
    sangría) no es su continuación, aunque el hueco y la sangría lo permitan."""
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_text("1. LAS ACOTACIONES VAN EN CENTIMETROS", height=0.1).set_placement((0.0, 10.0))
    msp.add_text("Y LOS NIVELES EN METROS.", height=0.1).set_placement((0.0, 9.78))
    msp.add_text("MATERIALES :", height=0.14).set_placement((0.4, 9.5))
    msp.add_text("1. CONCRETO CLASE 1", height=0.1).set_placement((0.0, 9.22))
    ruta = tmp_path / "titulo.dxf"
    doc.saveas(ruta)
    notas, _ = leer_notas(_textos(DxfParser().parse_file(ruta).entities), _hoja_de_prueba)
    clave = {(n.seccion, n.numero): n.texto for n in notas}
    assert clave == {
        ("", 1): "LAS ACOTACIONES VAN EN CENTIMETROS Y LOS NIVELES EN METROS.",
        ("MATERIALES", 1): "CONCRETO CLASE 1",
    }


def test_numbering_restarts_under_each_heading(tmp_path):
    grupos = [
        ("NOTAS GENERALES DE ESTRUCTURA.", ["1. ACOTACIONES EN CM", "2. NIVELES EN METROS"]),
        ("MATERIALES :", ["1. CONCRETO CLASE 1", "2. ACERO FY=4200"]),
        ("REFUERZO :", ["1. EN TRABES NO SE DEBERA SOLDAR", "ni acoplar"]),
    ]
    notas, contradicciones = leer_notas(_textos(_notas_dxf(tmp_path, grupos)), lambda e: "ES-001")
    clave = {(n.seccion, n.numero): n.texto for n in notas}
    assert clave == {
        ("NOTAS GENERALES DE ESTRUCTURA", 1): "ACOTACIONES EN CM",
        ("NOTAS GENERALES DE ESTRUCTURA", 2): "NIVELES EN METROS",
        ("MATERIALES", 1): "CONCRETO CLASE 1",
        ("MATERIALES", 2): "ACERO FY=4200",
        ("REFUERZO", 1): "EN TRABES NO SE DEBERA SOLDAR ni acoplar",
    }
    assert contradicciones == []  # el mismo número bajo otro encabezado no es otra redacción


def test_marina_geometry_indents_slack_and_tall_headings(tmp_path):
    """Como en Marina: renglones de 0.0775 con paso 0.153, continuaciones con tres espacios y
    un pelo de más a la derecha, la lista de recubrimientos con sangría (0.24) y los encabezados
    más altos (0.143) y desplazados 0.4 a la derecha."""
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    def linea(texto, x, y, alto=0.0775):
        msp.add_text(texto, height=alto).set_placement((x, y))

    linea("NOTAS GENERALES DE ESTRUCTURA.", 274.248, 91.764, 0.1428)
    linea("1.  ACOTACIONES EN CENTIMETROS, NIVELES  EN METROS.", 273.844, 91.586)
    # (las notas 2 y 3 ocupan el espacio entre la 1 y la 4: sin ellas habría un hueco de cinco
    # renglones, que es donde un bloque acaba)
    linea("2.  TODAS LAS ACOTACIONES, NIVELES Y PAÑOS FIJOS DEBERAN VERIFICARSE", 273.843, 91.433)
    linea("   CON LOS PLANOS ARQUITECTONICOS.", 273.880, 91.280)
    linea("3.  LOS ESQUEMAS DE LOS ELEMENTOS EN LOS QUE SE INDICA NO", 273.842, 91.127)
    linea("   ESTAN A ESCALA.", 273.880, 90.974)
    linea("4.  EL RECUBRIMIENTO MINIMO LIBRE, NO SERA MENOR QUE EL DIAMETRO DEL", 273.877, 90.802)
    linea("   REFUERZO LONGITUDINAL NI MENOR A:", 273.880, 90.649)
    linea("5.0 CM EN ELEMENTOS ESTRUCTURALES DE CIMENTACION", 274.119, 90.496)
    linea("5.0 CM EN COLUMNAS, EN CASO DE USAR PAQUETES DE VARILLAS SERA 1.5", 274.122, 90.343)
    linea("VECES EL DIAMETRO DE LA BARRA MAS GRUESA.", 274.124, 90.189)
    linea("4.0 CM EN TRABES Y LOSAS", 274.117, 90.036)
    linea("3.0 A 5.0 CM EN CASTILLOS, CADENAS, DALAS Y CERRAMIENTOS", 274.117, 89.883)
    linea("5.  EN TODOS LOS ELEMENTOS DE CONCRETO EL CURADO DEBERA  MANTENERSE", 273.870, 89.730)
    linea("   POR LO MENOS DURANTE LOS PRIMEROS 7 DIAS DESPUES DEL COLADO.", 273.880, 89.577)
    linea("   EL CONCRETO ALCANCE EL 80%%% DE LA RESISTENCIA ESPECIFICADA.", 273.880, 88.964)
    linea("( VERIFICAR CON PRUEBAS DE LABORATORIO )", 274.868, 88.812)
    linea("MATERIALES :", 273.904, 88.186, 0.1428)
    linea("REFUERZO :", 273.903, 86.432, 0.1428)
    linea("1.  EN TRABES NO SE DEBERA SOLDAR O ACOPLAR MAS DEL 50 %%% DEL", 273.842, 86.196)
    linea("   REFUERZO LONGITUDINAL EN UNA SOLA SECCION, LA DISTANCIA ENTRE", 273.879, 86.043)
    ruta = tmp_path / "geometria.dxf"
    doc.saveas(ruta)
    notas, contradicciones = leer_notas(
        _textos(DxfParser().parse_file(ruta).entities), _hoja_de_prueba
    )
    clave = {(n.seccion, n.numero): n.texto for n in notas}
    assert set(clave) == {
        ("NOTAS GENERALES DE ESTRUCTURA", 1),
        ("NOTAS GENERALES DE ESTRUCTURA", 2),
        ("NOTAS GENERALES DE ESTRUCTURA", 3),
        ("NOTAS GENERALES DE ESTRUCTURA", 4),
        ("NOTAS GENERALES DE ESTRUCTURA", 5),
        ("REFUERZO", 1),
    }
    assert clave[("NOTAS GENERALES DE ESTRUCTURA", 4)].endswith(
        "3.0 A 5.0 CM EN CASTILLOS, CADENAS, DALAS Y CERRAMIENTOS"
    )
    assert "NI MENOR A: 5.0 CM EN ELEMENTOS" in clave[("NOTAS GENERALES DE ESTRUCTURA", 4)]
    # La nota 5 llega hasta su segundo renglón; el hueco la corta antes de «EL CONCRETO ALCANCE».
    assert clave[("NOTAS GENERALES DE ESTRUCTURA", 5)].endswith("DESPUES DEL COLADO.")
    assert (
        clave[("REFUERZO", 1)].endswith("LA DISTANCIA ENTRE")
        and "50 % DEL" in clave[("REFUERZO", 1)]
    )
    assert contradicciones == []


def _hoja_de_prueba(e):
    return "ES-001"


def test_identical_copies_are_counted_once_with_their_hojas(tmp_path):
    entidades = _lineas(tmp_path, MARINA_REFUERZO, heading="REFUERZO :", copias=3)
    notas, contradicciones = leer_notas(_textos(entidades), _hoja_por_bloque)
    assert contradicciones == [] and [n.numero for n in notas] == [3, 4, 7]
    n4 = notas[1]
    assert n4.copias == 3 and n4.hojas == ["ES-001", "ES-002", "ES-003"] and n4.hoja == "ES-001"
    assert len(n4.entidades) == 4  # las de la primera copia, no las 12


def test_copies_that_say_different_things_are_reported_with_what_changed(tmp_path):
    doc = ezdxf.new("R2010")
    for nombre, tope, desde in (("A", "#6", "#8"), ("B", "#8", "#10")):
        renglones = [r.replace("#6", tope).replace("#8", desde, 1) for r in MARINA_REFUERZO]
        renglones[4] = f"HASTA EL {tope}, DEL {desde} Y DIAMETROS MAYORES SE SOLDARAN"
        _escribir_notas(doc.blocks.new(f"NOTAS_{nombre}"), [("REFUERZO :", renglones)])
    msp = doc.modelspace()
    for i, nombre in enumerate("AAB"):
        msp.add_blockref(f"NOTAS_{nombre}", (100.0 * i, 0.0))
    ruta = tmp_path / "difieren.dxf"
    doc.saveas(ruta)
    notas, contradicciones = leer_notas(
        _textos(DxfParser().parse_file(ruta).entities), _hoja_por_bloque
    )
    n4 = sorted((n for n in notas if n.numero == 4), key=lambda n: -n.copias)
    assert [(n.copias, n.hojas) for n in n4] == [(2, ["ES-001", "ES-002"]), (1, ["ES-003"])]
    (frase,) = contradicciones
    assert "nota 4 de REFUERZO" in frase
    assert "ES-001, ES-002" in frase and "ES-003" in frase  # dice dónde está cada redacción
    assert "#6, DEL #8" in frase and "#8, DEL #10" in frase  # y qué cambia
    assert "NO SE PERMITIRA" not in frase  # no repite lo que coincide


def test_two_unrelated_notes_that_share_a_number_are_not_a_contradiction(tmp_path):
    grupos = [
        ("REFUERZO :", ["1. EN TRABES NO SE DEBERA SOLDAR O ACOPLAR MAS DEL 50% DEL REFUERZO"]),
        ("REFUERZO :", ["1. LAS ACOTACIONES SE DAN EN CENTIMETROS Y LOS NIVELES EN METROS"]),
    ]
    notas, contradicciones = leer_notas(_textos(_notas_dxf(tmp_path, grupos)), _hoja_de_prueba)
    assert len(notas) == 2 and contradicciones == []


def test_a_numbered_line_without_a_heading_is_a_note_of_its_sheet_not_a_copy(tmp_path):
    doc = ezdxf.new("R2010")
    for nombre, peralte in (("A", "H=30"), ("B", "H=35 Y 45")):
        bloque = doc.blocks.new(nombre)
        texto = f"1. LOSA DE PERALTE TOTAL {peralte} CMS. ALIGERADA CON CASETON DE POLIESTIRENO"
        _escribir_notas(bloque, [(None, [texto])])
    msp = doc.modelspace()
    msp.add_blockref("A", (0.0, 0.0))
    msp.add_blockref("B", (100.0, 0.0))
    ruta = tmp_path / "sin_titulo.dxf"
    doc.saveas(ruta)
    notas, contradicciones = leer_notas(
        _textos(DxfParser().parse_file(ruta).entities), _hoja_por_bloque
    )
    assert [(n.seccion, n.numero, n.hojas) for n in notas] == [
        ("", 1, ["ES-001"]),
        ("", 1, ["ES-002"]),
    ]
    assert contradicciones == []  # cada hoja tiene su peralte: no es una versión de la otra


def test_a_line_without_a_number_or_a_note_to_continue_is_not_a_note(tmp_path):
    grupos = [("REFUERZO :", ["TEXTO SUELTO SIN NUMERO", "OTRO MAS"])]
    notas, contradicciones = leer_notas(_textos(_notas_dxf(tmp_path, grupos)), _hoja_de_prueba)
    assert notas == [] and contradicciones == []


# --- Reglas: la tabla, las notas y lo que el plano declara ----------------------------------------

MARINA_PB_GENERALES = [
    "4. EL RECUBRIMIENTO MINIMO LIBRE, NO SERA MENOR QUE EL DIAMETRO DEL",
    "REFUERZO LONGITUDINAL NI MENOR A:",
    "5.0 CM EN ELEMENTOS ESTRUCTURALES DE CIMENTACION",
    "5.0 CM LIBRES EN COLUMNAS, EN CASO DE USAR PAQUETES DE VARILLAS SERA ",
    "1.5 VECES EL DIAMETRO DE LA BARRA MAS GRUESA.",
    "4.0 CM EN TRABES Y LOSAS",
    "3.0 A 5.0 CM LIBRES EN CASTILLOS Y 3.0CM EN CADENAS, DALAS Y CERRAMIENTOS",
    "5. EN TODOS LOS ELEMENTOS DE CONCRETO EL CURADO DEBERA MANTENERSE",
]
MARINA_PB_REFUERZO = [r.replace("#6, DEL #8", "#8, DEL #10") for r in MARINA_REFUERZO]
ANCLAJE_DE_CASTILLO = "\\A1;100CM\\PANCLAJE DE\\P CASTILLO"
PLANTILLA = "PLANTILLA 5 CMS.  F'C=100 KG/CM2"


def _dibujo(
    tmp_path,
    *,
    tabla=True,
    bloques=(),
    mtexts=(),
    textos=(),
    dimensiones=(),
    tabla_kw=None,
    separacion=100.0,
):
    """Un dibujo con la tabla de Marina (si ``tabla``), bloques de notas ``(grupos, copias)``
    —cada copia 100 a la derecha de la anterior— y textos sueltos."""
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    if tabla:
        _bloque(doc, "TABLA", **(tabla_kw or {}))
        msp.add_blockref("TABLA", (0.0, 0.0))
    for k, (grupos, copias) in enumerate(bloques):
        bloque = doc.blocks.new(f"NOTAS_{k}")
        _escribir_notas(bloque, grupos)
        for i in range(copias):
            msp.add_blockref(f"NOTAS_{k}", (50.0 + separacion * i, 40.0 - 60.0 * k))
    for texto, x, y in mtexts:
        msp.add_mtext(texto).set_location((x, y))
    for texto, x, y in textos:
        msp.add_text(texto, height=0.1).set_placement((x, y))
    for texto, x, y in dimensiones:
        msp.add_linear_dim(base=(x, y + 1), p1=(x, y), p2=(x + 1, y), text=texto).render()
    ruta = tmp_path / "marina.dxf"
    doc.saveas(ruta)
    return DxfParser().parse_file(ruta).entities


def _marina_notes_and_table(tmp_path):
    grupos = [
        ("NOTAS GENERALES DE ESTRUCTURA.", MARINA_GENERALES),
        ("REFUERZO :", MARINA_REFUERZO),
    ]
    return _dibujo(
        tmp_path,
        bloques=[(grupos, 1)],
        mtexts=[(ANCLAJE_DE_CASTILLO, 20.0, 20.0)],
        textos=[(PLANTILLA, 20.0, 10.0)],
    )


def test_marina_rules(tmp_path):
    r = leer_reglas(_marina_notes_and_table(tmp_path), frames=[])
    cov = {k: (d.valor, d.fuente) for k, d in r.recubrimiento_m.items()}
    assert cov["zapata"] == cov["dado"] == cov["pilote"] == cov["contratrabe"] == (0.05, "nota")
    assert cov["losa_cimentacion"] == (0.05, "nota")
    assert cov["columna"] == (0.05, "nota") and cov["trabe"] == cov["losa"] == (0.04, "nota")
    assert cov["castillo"] == cov["dala"] == cov["cerramiento"] == (0.03, "nota")
    assert cov["muro_concreto"] == (0.04, "supuesto")
    assert any("3.0 a 5.0" in a for a in r.avisos)
    assert r.traslape_max_numero.valor == "6" and r.soldar_desde_numero.valor == "8"
    assert sorted(r.primer_estribo_m) == ["contratrabe", "trabe"]
    assert r.primer_estribo_m["trabe"].valor == r.primer_estribo_m["contratrabe"].valor == 0.06
    assert r.gancho_estribo.valor == {"angulo": 135, "recto_diametros": 10}
    assert r.gancho_estribo.fuente == "nota"
    assert r.gancho_grapa.valor == {"angulo": 180, "recto_diametros": 10}
    assert r.gancho_grapa.fuente == "nota"
    assert r.anclajes_declarados_m["castillo"].valor == 1.00  # «100CM ANCLAJE DE CASTILLO»
    assert r.plantilla_espesor_m.valor == 0.05  # «PLANTILLA 5 CMS. F'C=100 KG/CM2»
    assert any("#8" in c and "suelda" in c for c in r.contradicciones)  # table lists LT for #8


def test_no_notes_means_supuestos():
    r = reglas_estandar()
    assert r.recubrimiento_m["castillo"].fuente == "supuesto" and r.soldar_desde_numero is None


def test_reglas_estandar_is_everything_supuesto():
    r = reglas_estandar()
    assert r.tabla_varillas.fuente == "supuesto" and r.tabla_varillas.valor["8"].LT1 is None
    assert set(r.recubrimiento_m) == set(RECUBRIMIENTO_SUPUESTO)
    for familia, dato in r.recubrimiento_m.items():
        assert dato.fuente == "supuesto" and dato.valor == RECUBRIMIENTO_SUPUESTO[familia]
    assert r.gancho_estribo.fuente == "supuesto"
    assert r.gancho_estribo.valor == {"angulo": 135, "recto_diametros": 10}
    assert r.gancho_grapa.fuente == "supuesto"
    assert r.gancho_grapa.valor == {"angulo": 180, "recto_diametros": 10}
    assert r.soldar_desde_numero is None and r.traslape_max_numero is None
    assert r.primer_estribo_m == {}
    assert r.anclajes_declarados_m == {} and r.plantilla_espesor_m is None
    assert r.contradicciones == [] and r.avisos == []
    r.recubrimiento_m["zapata"].valor = 9.0  # una copia: nadie corrompe el supuesto
    assert reglas_estandar().recubrimiento_m["zapata"].valor == 0.05


def test_reglas_survive_a_trip_through_json(tmp_path):
    import json

    r = leer_reglas(_marina_notes_and_table(tmp_path), frames=[])
    vuelta = Reglas.model_validate(json.loads(json.dumps(r.model_dump(mode="json"))))
    assert vuelta.soldar_desde_numero.valor == "8"
    assert sorted(vuelta.primer_estribo_m) == ["contratrabe", "trabe"]
    assert vuelta.recubrimiento_m["castillo"].valor == 0.03
    assert vuelta.tabla_varillas.valor["8"]["LT1"] == 115  # tras recargar, las filas son dicts
    assert vuelta.contradicciones == r.contradicciones and vuelta.avisos == r.avisos


def test_the_supuesto_covers_are_the_ones_of_the_brief():
    assert RECUBRIMIENTO_SUPUESTO == {
        "zapata": 0.05,
        "dado": 0.05,
        "pilote": 0.05,
        "contratrabe": 0.05,
        "losa_cimentacion": 0.05,
        "columna": 0.05,
        "trabe": 0.04,
        "losa": 0.04,
        "muro_concreto": 0.04,
        "castillo": 0.03,
        "dala": 0.03,
        "cerramiento": 0.03,
    }


def test_a_drawing_with_no_notes_and_no_table_is_the_standard(tmp_path):
    entidades = _dibujo(tmp_path, tabla=False, textos=[("HOLA", 0.0, 0.0)])
    r = leer_reglas(entidades, frames=[])
    assert r.model_dump() == reglas_estandar().model_dump()


def test_a_note_with_a_source_carries_where_it_is_and_how_many_copies(tmp_path):
    grupos = [("NOTAS GENERALES DE ESTRUCTURA.", MARINA_GENERALES), ("REFUERZO :", MARINA_REFUERZO)]
    entidades = _dibujo(tmp_path, bloques=[(grupos, 3)])
    ids = {e.entity_id: e.text for e in entidades if e.is_textual}
    r = leer_reglas(entidades, frames=[])
    zapata = r.recubrimiento_m["zapata"]
    assert zapata.copias == 3 and zapata.en_conflicto is False
    assert "5.0 CM EN ELEMENTOS ESTRUCTURALES DE CIMENTACION" in zapata.texto
    assert all(i in ids for i in zapata.entidades) and zapata.entidades
    assert r.soldar_desde_numero.copias == 3 and r.soldar_desde_numero.hoja == "marina.dxf"
    assert "SE SOLDARAN" in r.soldar_desde_numero.texto
    assert r.primer_estribo_m["trabe"].copias == 3 and r.gancho_estribo.copias == 3


def test_the_hoja_of_a_rule_is_the_sheet_frame_that_holds_the_note(tmp_path):
    from klave_engine.detection.frames import SheetFrame

    grupos = [("REFUERZO :", MARINA_REFUERZO)]
    entidades = _dibujo(tmp_path, tabla=False, bloques=[(grupos, 2)])
    marcos = [
        SheetFrame(
            frame_id="frame_00", bbox=(0, -100, 100, 100), source_file="marina.dxf", code="ES-001"
        ),
        SheetFrame(
            frame_id="frame_01", bbox=(100, -100, 200, 100), source_file="marina.dxf", code="ES-002"
        ),
    ]
    r = leer_reglas(entidades, frames=marcos)
    assert r.soldar_desde_numero.copias == 2 and r.soldar_desde_numero.hoja == "ES-001"


# --- recubrimientos ---------------------------------------------------------------------------


def test_covers_in_the_wording_of_the_pb_sheets_are_read_per_word(tmp_path):
    grupos = [("NOTAS GENERALES DE ESTRUCTURA.", MARINA_PB_GENERALES)]
    r = leer_reglas(_dibujo(tmp_path, tabla=False, bloques=[(grupos, 1)]), frames=[])
    cov = {k: d.valor for k, d in r.recubrimiento_m.items() if d.fuente == "nota"}
    assert cov == {
        "zapata": 0.05,
        "dado": 0.05,
        "pilote": 0.05,
        "contratrabe": 0.05,
        "losa_cimentacion": 0.05,
        "columna": 0.05,
        "trabe": 0.04,
        "losa": 0.04,
        "castillo": 0.03,
        "dala": 0.03,
        "cerramiento": 0.03,
    }
    # Sólo el castillo va de 3.0 a 5.0; las cadenas, dalas y cerramientos son 3.0 sin rango.
    (aviso,) = [a for a in r.avisos if "3.0 a 5.0" in a]
    assert "castillo" in aviso and "dala" not in aviso and "mínimo" in aviso


def test_a_cover_range_takes_its_minimum_and_says_so(tmp_path):
    r = leer_reglas(_marina_notes_and_table(tmp_path), frames=[])
    (aviso,) = [a for a in r.avisos if "3.0 a 5.0" in a]
    assert "castillo" in aviso and "dala" in aviso and "cerramiento" in aviso
    assert "3.0 cm" in aviso and "mínimo" in aviso
    assert r.contradicciones != [] and all("3.0 a 5.0" not in c for c in r.contradicciones)


def test_covers_keep_the_supuesto_for_the_families_the_notes_do_not_name(tmp_path):
    r = leer_reglas(_marina_notes_and_table(tmp_path), frames=[])
    supuestos = {k for k, d in r.recubrimiento_m.items() if d.fuente == "supuesto"}
    assert supuestos == {"muro_concreto"}
    assert r.recubrimiento_m["muro_concreto"].valor == RECUBRIMIENTO_SUPUESTO["muro_concreto"]


def test_two_copies_that_disagree_on_a_cover_are_flagged_never_picked_silently(tmp_path):
    distinta = [
        r.replace("4.0 CM EN TRABES Y LOSAS", "5.0 CM EN TRABES Y LOSAS") for r in MARINA_GENERALES
    ]
    doc = ezdxf.new("R2010")
    for nombre, renglones in (("A", MARINA_GENERALES), ("B", distinta)):
        _escribir_notas(doc.blocks.new(nombre), [("NOTAS GENERALES DE ESTRUCTURA.", renglones)])
    msp = doc.modelspace()
    for i, nombre in enumerate("AAB"):
        msp.add_blockref(nombre, (100.0 * i, 0.0))
    ruta = tmp_path / "marina.dxf"
    doc.saveas(ruta)
    r = leer_reglas(DxfParser().parse_file(ruta).entities, frames=[])
    trabe = r.recubrimiento_m["trabe"]
    assert trabe.en_conflicto is True and trabe.valor == 0.04 and trabe.copias == 2
    assert [a.valor for a in trabe.alternativas] == [0.05]
    assert r.recubrimiento_m["losa"].en_conflicto is True
    assert r.recubrimiento_m["columna"].en_conflicto is False
    frase = next(c for c in r.contradicciones if "recubrimiento de trabe" in c)
    assert "4 cm" in frase and "5 cm" in frase
    assert any("nota 4" in c and "4.0" in c and "5.0" in c for c in r.contradicciones)  # y el texto


def test_an_implausible_cover_is_not_used_and_is_reported(tmp_path):
    renglones = ["4. EL RECUBRIMIENTO MINIMO SERA 50 CM EN TRABES Y 5.0 CM EN COLUMNAS"]
    r = leer_reglas(
        _dibujo(tmp_path, tabla=False, bloques=[([("NOTAS :", renglones)], 1)]), frames=[]
    )
    assert r.recubrimiento_m["trabe"].fuente == "supuesto"
    assert (
        r.recubrimiento_m["columna"].fuente == "nota" and r.recubrimiento_m["columna"].valor == 0.05
    )
    assert any("50" in a and "trabe" in a for a in r.avisos)


def test_a_cover_list_ends_where_the_sentence_does(tmp_path):
    renglones = [
        "4. EL RECUBRIMIENTO MINIMO SERA 5.0 CM EN COLUMNAS, EN CASO DE USAR PAQUETES SE",
        "CONSIDERARA LA BARRA MAS GRUESA DE LOS CASTILLOS.",
    ]
    r = leer_reglas(
        _dibujo(tmp_path, tabla=False, bloques=[([("NOTAS :", renglones)], 1)]), frames=[]
    )
    assert (
        r.recubrimiento_m["columna"].valor == 0.05 and r.recubrimiento_m["columna"].fuente == "nota"
    )
    assert r.recubrimiento_m["castillo"].fuente == "supuesto"  # el castillo es de otra frase


def test_a_cover_note_in_another_wording_is_reported_not_dropped(tmp_path):
    renglones = [
        "4. EL RECUBRIMIENTO LIBRE DE LAS VARILLAS SERA DE 3 CM",
        "5. EL RECUBRIMIENTO VA EN DETALLE",
    ]
    r = leer_reglas(
        _dibujo(tmp_path, tabla=False, bloques=[([("NOTAS :", renglones)], 1)]), frames=[]
    )
    assert all(d.fuente == "supuesto" for d in r.recubrimiento_m.values())
    (aviso,) = r.avisos  # la nota 5 no trae medida: no hay nada que leer ni que avisar
    assert "La nota 4 de NOTAS" in aviso and "recubrimiento" in aviso


def test_a_cover_for_elements_nobody_recognises_is_reported(tmp_path):
    renglones = ["4. EL RECUBRIMIENTO MINIMO SERA 5.0 CM EN ALBERCAS"]
    r = leer_reglas(
        _dibujo(tmp_path, tabla=False, bloques=[([("NOTAS :", renglones)], 1)]), frames=[]
    )
    assert all(d.fuente == "supuesto" for d in r.recubrimiento_m.values())
    assert any("ALBERCAS" in a for a in r.avisos)


def test_a_cover_line_in_a_note_that_does_not_talk_about_covers_is_not_a_cover(tmp_path):
    renglones = ["1. EL ANCLAJE SERA DE 30 CM EN COLUMNAS DE ORILLA"]
    r = leer_reglas(
        _dibujo(tmp_path, tabla=False, bloques=[([("NOTAS :", renglones)], 1)]), frames=[]
    )
    assert r.recubrimiento_m["columna"].fuente == "supuesto" and r.avisos == []


# --- traslape, soldadura, primer estribo, ganchos -----------------------------------------------


def _con_notas(tmp_path, renglones, titulo="REFUERZO :", **kw):
    return leer_reglas(
        _dibujo(tmp_path, tabla=False, bloques=[([(titulo, renglones)], 1)], **kw), frames=[]
    )


def test_lap_and_weld_numbers_are_read_from_the_note(tmp_path):
    r = _con_notas(tmp_path, MARINA_PB_REFUERZO)
    assert r.traslape_max_numero.valor == "8" and r.soldar_desde_numero.valor == "10"
    assert r.traslape_max_numero.fuente == "nota" and "HASTA EL #8" in r.traslape_max_numero.texto
    assert r.soldar_desde_numero.fuente == "nota"


def test_a_bar_number_in_the_lap_note_that_is_not_a_bar_is_reported(tmp_path):
    renglones = [
        "4. UNICAMENTE SE PERMITIRA TRASLAPAR VARILLA",
        "HASTA EL #9, DEL #10 Y DIAMETROS MAYORES SE SOLDARAN",
    ]
    r = _con_notas(tmp_path, renglones)
    assert r.traslape_max_numero is None and r.soldar_desde_numero.valor == "10"
    assert any("#9" in a and "no es un número de varilla" in a for a in r.avisos)


def test_the_weld_note_against_the_table_is_a_contradiction_not_an_aviso(tmp_path):
    r = leer_reglas(_marina_notes_and_table(tmp_path), frames=[])
    frase = (
        "La tabla de varillas da traslape para #8, "
        "pero la nota dice que del #8 en adelante se suelda."
    )
    assert frase in r.contradicciones
    assert all("suelda" not in a for a in r.avisos)


def test_the_weld_note_agrees_with_the_table_when_the_laps_stop_where_the_welds_begin(tmp_path):
    grupos = [("REFUERZO :", MARINA_PB_REFUERZO)]  # lap hasta #8, solda desde #10
    r = leer_reglas(_dibujo(tmp_path, bloques=[(grupos, 1)]), frames=[])
    assert r.soldar_desde_numero.valor == "10"
    assert not any("suelda" in c for c in r.contradicciones)


def test_a_table_that_is_only_the_standard_does_not_contradict_a_weld_note(tmp_path):
    # Sin tabla en el plano, la estándar (sin LT desde #8) es supuesto: no se contradice a sí misma.
    r = leer_reglas(
        _dibujo(tmp_path, tabla=False, bloques=[([("REFUERZO :", MARINA_REFUERZO)], 1)]), frames=[]
    )
    assert r.tabla_varillas.fuente == "supuesto"
    assert r.soldar_desde_numero.valor == "8" and r.contradicciones == []


def test_the_table_contradiction_lists_every_bar_with_a_lap_at_or_above_the_weld_bar(tmp_path):
    renglones = [
        "4. UNICAMENTE SE PERMITIRA TRASLAPAR VARILLA",
        "HASTA EL #5, DEL #6 Y DIAMETROS MAYORES SE SOLDARAN",
    ]
    r = leer_reglas(_dibujo(tmp_path, bloques=[([("REFUERZO :", renglones)], 1)]), frames=[])
    (frase,) = [c for c in r.contradicciones if "suelda" in c]
    assert "#6 y #8" in frase and "del #6 en adelante" in frase


def test_the_first_stirrup_is_one_value_per_family(tmp_path):
    r = _con_notas(tmp_path, MARINA_REFUERZO)
    assert sorted(r.primer_estribo_m) == [
        "contratrabe",
        "trabe",
    ]  # «EN TRABES» incluye contratrabes
    for dato in r.primer_estribo_m.values():
        assert dato.valor == 0.06 and dato.fuente == "nota"
        assert "PRIMER ESTRIBO A 6 CMS" in dato.texto and dato.entidades


def test_a_first_stirrup_note_for_other_elements(tmp_path):
    renglones = ["3. EN COLUMNAS Y CASTILLOS EL PRIMER ESTRIBO SE COLOCARA A 5 CM DEL PAÑO"]
    r = _con_notas(tmp_path, renglones)
    assert {f: d.valor for f, d in r.primer_estribo_m.items()} == {
        "columna": 0.05,
        "castillo": 0.05,
    }


def test_a_first_stirrup_that_differs_by_family_is_not_a_conflict(tmp_path):
    renglones = [
        "3. EN TRABES LA SEPARACION DE LOS ESTRIBOS EMPEZARA A PARTIR DEL PAÑO, COLOCANDO EL",
        "PRIMER ESTRIBO A 6 CMS.",
        "4. EN COLUMNAS EL PRIMER ESTRIBO SE COLOCARA A 5 CMS. DEL PAÑO",
    ]
    r = _con_notas(tmp_path, renglones)
    assert {f: d.valor for f, d in r.primer_estribo_m.items()} == {
        "trabe": 0.06,
        "contratrabe": 0.06,
        "columna": 0.05,
    }
    assert all(not d.en_conflicto for d in r.primer_estribo_m.values())
    assert r.contradicciones == []


def test_a_first_stirrup_without_families_is_reported_and_not_used(tmp_path):
    r = _con_notas(tmp_path, ["3. EL PRIMER ESTRIBO A 6 CMS. DEL PAÑO"])
    assert r.primer_estribo_m == {}
    assert any("primer estribo" in a.lower() and "no dice" in a for a in r.avisos)


def test_hooks_follow_the_order_the_note_names_stirrups_and_grapas(tmp_path):
    renglones = [
        "7. EL ANCLAJE DE GRAPAS Y ESTRIBOS SE HARA CON UN DOBLEZ A 180° Y 135°",
        "SEGUIDO DE UN TRAMO RECTO DE 6 DIAMETROS",
    ]
    r = _con_notas(tmp_path, renglones)
    assert r.gancho_estribo.valor == {"angulo": 135, "recto_diametros": 6}
    assert r.gancho_grapa.valor == {"angulo": 180, "recto_diametros": 6}


def test_the_hook_carries_the_text_it_was_read_from(tmp_path):
    r = _con_notas(tmp_path, MARINA_REFUERZO)
    assert "DOBLEZ A 135° Y 180°" in r.gancho_estribo.texto
    assert r.gancho_estribo.texto.endswith("RECTO DE 10Ø")
    assert r.gancho_estribo.entidades and r.gancho_estribo.texto == r.gancho_grapa.texto


def test_where_things_are_names_a_few_sheets_and_counts_the_rest():
    from klave_engine.estructura.notas import donde_estan

    assert donde_estan(["ES-002", "ES-001"]) == "ES-001, ES-002"
    muchas = [f"ES-{n:03d}" for n in range(1, 13)]
    assert donde_estan(muchas) == "ES-001, ES-002, ES-003 y 9 hojas más"


def test_a_hook_note_without_the_straight_leg_keeps_the_standard_leg_and_says_so(tmp_path):
    renglones = ["7. EL ANCLAJE DE ESTRIBOS Y GRAPAS SE HARA CON UN DOBLEZ A 135° Y 180°"]
    r = _con_notas(tmp_path, renglones)
    assert r.gancho_estribo.valor == {"angulo": 135, "recto_diametros": 10}
    assert r.gancho_estribo.fuente == "nota"
    assert any("tramo recto" in a for a in r.avisos)


def test_a_hook_note_that_does_not_say_which_is_which_is_reported_not_guessed(tmp_path):
    renglones = ["7. EL ANCLAJE SE HARA CON UN DOBLEZ A 135° Y 180° Y UN TRAMO RECTO DE 10Ø"]
    r = _con_notas(tmp_path, renglones)
    assert r.gancho_estribo.fuente == "supuesto" and r.gancho_grapa.fuente == "supuesto"
    assert any("estribos" in a.lower() and "grapas" in a.lower() for a in r.avisos)


# --- anclajes declarados y plantilla ------------------------------------------------------------


def test_the_castillo_anchorage_is_read_from_a_dimension_override_text(tmp_path):
    # Como en Marina: la cota 100 con el texto «100CM\PANCLAJE DE\P CASTILLO».
    entidades = _dibujo(tmp_path, tabla=False, dimensiones=[(ANCLAJE_DE_CASTILLO, 20.0, 20.0)])
    dimension = next(e for e in entidades if e.entity_type.value == "dimension")
    assert "ANCLAJE" in dimension.properties["display_text"]
    r = leer_reglas(entidades, frames=[])
    dato = r.anclajes_declarados_m["castillo"]
    assert dato.valor == 1.00 and dato.fuente == "detalle"
    assert dato.entidades == [dimension.entity_id] and "CASTILLO" in dato.texto


@pytest.mark.parametrize(
    ("texto", "familia", "valor"),
    [
        ("\\A1;100CM\\PANCLAJE DE\\P CASTILLO", "castillo", 1.0),
        ("60 CM ANCLAJE DE COLUMNA", "columna", 0.6),
        ("ANCLAJE DE CASTILLO 80CM", "castillo", 0.8),
        ("45cm\\Panclaje de\\Pdalas", "dala", 0.45),
    ],
)
def test_anchorage_wordings(tmp_path, texto, familia, valor):
    r = leer_reglas(_dibujo(tmp_path, tabla=False, mtexts=[(texto, 5.0, 5.0)]), frames=[])
    assert r.anclajes_declarados_m[familia].valor == valor


def test_an_anchorage_label_without_a_length_is_not_a_declared_anchorage(tmp_path):
    r = leer_reglas(
        _dibujo(tmp_path, tabla=False, mtexts=[("ANCLAJE DE\\PCASTILLO", 5.0, 5.0)]), frames=[]
    )
    assert r.anclajes_declarados_m == {}


def test_two_anchorage_labels_that_disagree_are_flagged(tmp_path):
    entidades = _dibujo(
        tmp_path,
        tabla=False,
        mtexts=[("100CM ANCLAJE DE CASTILLO", 5.0, 5.0), ("80CM ANCLAJE DE CASTILLO", 15.0, 5.0)],
    )
    r = leer_reglas(entidades, frames=[])
    dato = r.anclajes_declarados_m["castillo"]
    assert dato.en_conflicto is True and len(dato.alternativas) == 1
    assert any(
        "anclaje de castillo" in c and "100 cm" in c and "80 cm" in c for c in r.contradicciones
    )


@pytest.mark.parametrize(
    "texto",
    [
        "PLANTILLA 5 CMS.  F'C=100 KG/CM2",
        "PLANTILLA 5 CM\\PDE ESP. DE CONCRETO\\PF'C=100 KG/CM2",
        "PLANTILLA 5 CM ESP.\\PCONCRETO F'C=100KG/CM2",
        "PLANTILLA DE CONCRETO\\PF'C=100 KG/CM2 ESPESOR 5 CM",
        "PLANTILLA DE 5 CM",
        "PLANTILLA DE CONCRETO POBRE DE 5 CM DE ESPESOR",
        "PLANTILLA DE 0.05 M",
        "PLANTILLA DE CONCRETO POBRE\\PESPESOR 0.05 M",
        "PLANTILLA DE CONCRETO POBRE DE 5 CMS. DE ESP.",
    ],
)
def test_plantilla_wordings(tmp_path, texto):
    r = leer_reglas(_dibujo(tmp_path, tabla=False, mtexts=[(texto, 5.0, 5.0)]), frames=[])
    assert r.plantilla_espesor_m.valor == 0.05 and r.plantilla_espesor_m.fuente == "detalle"


def test_plantilla_copies_are_counted_and_a_different_one_is_flagged(tmp_path):
    entidades = _dibujo(
        tmp_path,
        tabla=False,
        mtexts=[
            ("PLANTILLA 5 CM", 5.0, 5.0),
            ("PLANTILLA 5 CM", 15.0, 5.0),
            ("PLANTILLA 8 CM", 25.0, 5.0),
        ],
    )
    r = leer_reglas(entidades, frames=[])
    dato = r.plantilla_espesor_m
    assert dato.valor == 0.05 and dato.copias == 2 and dato.en_conflicto is True
    assert any("plantilla" in c and "5 cm" in c and "8 cm" in c for c in r.contradicciones)


def test_a_plantilla_text_without_a_thickness_is_not_a_reading(tmp_path):
    r = leer_reglas(
        _dibujo(tmp_path, tabla=False, mtexts=[("PLANTILLA DE CONCRETO POBRE", 5, 5)]), frames=[]
    )
    assert r.plantilla_espesor_m is None and r.avisos == []


def test_plantilla_inside_a_numbered_note_is_a_nota_not_a_detalle(tmp_path):
    renglones = [
        "2. BAJO LA CIMENTACION SE COLOCARA PLANTILLA DE",
        "CONCRETO POBRE, PLANTILLA 7 CM DE ESPESOR.",
    ]
    r = _con_notas(tmp_path, renglones, titulo="NOTAS :")
    assert r.plantilla_espesor_m.valor == 0.07 and r.plantilla_espesor_m.fuente == "nota"


# --- la tabla de varillas dentro de Reglas ---------------------------------------------------


def test_the_table_of_the_drawing_wins_and_a_missing_bar_comes_from_the_standard(tmp_path):
    r = leer_reglas(_dibujo(tmp_path, tabla_kw={"sin": ("4",)}), frames=[])
    tabla = r.tabla_varillas
    assert tabla.fuente == "cuadro"  # la tabla del plano se leyó
    assert (
        tabla.valor["4"] == TABLA_ESTANDAR["4"] and tabla.valor["8"].LT1 == 115
    )  # el #8 es del plano
    assert tabla.valor["4"] is not TABLA_ESTANDAR["4"]  # una copia
    assert "#4" in tabla.texto and "estándar" in tabla.texto
    (aviso,) = [a for a in r.avisos if "estándar" in a]
    assert "#4" in aviso and "supuesto" in aviso and r.contradicciones == []


def test_a_bar_neither_the_drawing_nor_the_standard_has_is_simply_absent(tmp_path):
    r = leer_reglas(_dibujo(tmp_path), frames=[])
    assert "7" not in r.tabla_varillas.valor and "2" not in r.tabla_varillas.valor
    assert sorted(r.tabla_varillas.valor, key=float) == ["2.5", "3", "4", "5", "6", "8", "10", "12"]
    assert r.avisos == [] and r.tabla_varillas.fuente == "cuadro"


def test_the_standard_rows_do_not_count_when_the_notes_are_checked_against_the_table(tmp_path):
    # La nota suelda desde el #6; la tabla del plano se queda sin #6 y sin #8, así que lo que
    # tiene de #6 en adelante (#10 y #12) no trae traslape. La fila #6 de la estándar, que sí lo
    # trae, entra en la tabla pero no cuenta: no es del plano.
    renglones = [
        "4. UNICAMENTE SE PERMITIRA TRASLAPAR VARILLA",
        "HASTA EL #5, DEL #6 Y DIAMETROS MAYORES SE SOLDARAN",
    ]
    grupos = [("REFUERZO :", renglones)]
    r = leer_reglas(
        _dibujo(tmp_path, tabla_kw={"sin": ("6", "8")}, bloques=[(grupos, 1)]), frames=[]
    )
    assert r.tabla_varillas.valor["6"].LT1 == TABLA_ESTANDAR["6"].LT1 == 70
    assert not any("suelda" in c for c in r.contradicciones)


def test_table_contradictions_and_avisos_stay_in_their_own_lists(tmp_path):
    doc_kw = {"cambio": {("8", "LT1"): "1l5"}}
    r = leer_reglas(_dibujo(tmp_path, tabla_kw=doc_kw), frames=[])
    assert r.tabla_varillas.valor["8"].LT1 is None
    assert any("1l5" in a for a in r.avisos) and r.contradicciones == []

    # Dos copias de la tabla que difieren: contradicción; nada de eso entre los avisos.
    doc = ezdxf.new("R2010")
    _bloque(doc, "A")
    _bloque(doc, "B", cambio={("8", "LT1"): 120})
    msp = doc.modelspace()
    msp.add_blockref("A", (0.0, 0.0))
    msp.add_blockref("B", (40.0, 0.0))
    ruta = tmp_path / "dos.dxf"
    doc.saveas(ruta)
    r2 = leer_reglas(DxfParser().parse_file(ruta).entities, frames=[])
    assert any("#8 LT1" in c for c in r2.contradicciones)
    assert r2.avisos == []
    assert r2.tabla_varillas.en_conflicto is True


# --- el dibujo de Marina, con sus bloques distintos ------------------------------------------


def _marcos_de_los_bloques():
    """Los marcos de ``_dibujo``: cimentación (2 copias) ES-001/002 y plantas (3) ES-101/102/103.
    Los hojas de plantas son mayores: si la mayoría no mandara, ganaría la cimentación."""
    from klave_engine.detection.frames import SheetFrame

    def marco(codigo, i, y0, y1):
        caja = (40.0 + 100.0 * i, y0, 140.0 + 100.0 * i, y1)
        return SheetFrame(frame_id=codigo, bbox=caja, source_file="marina.dxf", code=codigo)

    return [
        *(marco(f"ES-00{i + 1}", i, 10.0, 60.0) for i in range(2)),
        *(marco(f"ES-10{i + 1}", i, -60.0, -10.0) for i in range(3)),
    ]


def test_marina_blocks_that_disagree_are_all_reported(tmp_path):
    """Las hojas de cimentación y las de plantas no dicen lo mismo del traslape y la soldadura
    (#6/#8 contra #8/#10): ninguna se escoge en silencio y todo queda a la vista."""
    cimentacion = [
        ("NOTAS GENERALES DE ESTRUCTURA.", MARINA_GENERALES),
        ("REFUERZO :", MARINA_REFUERZO),
    ]
    plantas = [
        ("NOTAS GENERALES DE ESTRUCTURA.", MARINA_PB_GENERALES),
        ("REFUERZO :", MARINA_PB_REFUERZO),
    ]
    entidades = _dibujo(tmp_path, bloques=[(cimentacion, 2), (plantas, 3)])
    r = leer_reglas(entidades, frames=_marcos_de_los_bloques())
    soldar = r.soldar_desde_numero
    # Gana la lectura que más hojas repiten (3 contra 2), aunque su hoja sea mayor.
    assert soldar.en_conflicto is True and soldar.valor == "10" and soldar.copias == 3
    assert soldar.hoja == "ES-101"
    assert [(a.valor, a.hoja, a.copias) for a in soldar.alternativas] == [("8", "ES-001", 2)]
    assert r.traslape_max_numero.valor == "8" and r.traslape_max_numero.en_conflicto is True
    columna = r.recubrimiento_m["columna"]
    assert columna.en_conflicto is False and columna.copias == 5
    assert r.gancho_estribo.en_conflicto is False

    textos = "\n".join(r.contradicciones)
    assert "nota 4 de REFUERZO" in textos  # la redacción cambia
    assert "la varilla desde la que se suelda" in textos and "#8" in textos and "#10" in textos
    assert "ES-101, ES-102, ES-103" in textos and "ES-001, ES-002" in textos
    assert "la varilla hasta la que se traslapa" in textos
    # La nota de cimentación (suelda desde #8) contradice la tabla, y se dice de qué hojas es.
    (tabla_vs_nota,) = [c for c in r.contradicciones if "La tabla de varillas da traslape" in c]
    assert "#8" in tabla_vs_nota and "(nota de ES-001, ES-002)" in tabla_vs_nota
    # La redacción distinta de los recubrimientos (LIBRES) también se cita, sin cambiar sus valores.
    assert any(
        "nota 4 de NOTAS GENERALES DE ESTRUCTURA" in c and "LIBRES" in c for c in r.contradicciones
    )


# --- R34 y la ronda de arreglos: cada hoja dice sus reglas, y lo que no se lee se avisa -----------


def test_every_rule_reading_knows_all_the_hojas_that_say_it(tmp_path):
    cimentacion = [("REFUERZO :", MARINA_REFUERZO)]
    plantas = [("REFUERZO :", MARINA_PB_REFUERZO)]
    r = leer_reglas(
        _dibujo(tmp_path, bloques=[(cimentacion, 2), (plantas, 3)]), frames=_marcos_de_los_bloques()
    )
    assert r.soldar_desde_numero.hojas == ["ES-101", "ES-102", "ES-103"]
    assert r.soldar_desde_numero.hoja == "ES-101"
    assert [(a.valor, a.hojas) for a in r.soldar_desde_numero.alternativas] == [
        ("8", ["ES-001", "ES-002"])
    ]
    # Las que las cinco hojas dicen igual (el gancho) las traen todas.
    assert sorted(r.gancho_estribo.hojas) == ["ES-001", "ES-002", "ES-101", "ES-102", "ES-103"]
    for dato in (r.gancho_grapa, r.traslape_max_numero, *r.primer_estribo_m.values()):
        assert dato.hojas and dato.hoja == dato.hojas[0]


def test_each_sheet_resolves_its_own_lap_and_weld_limits(tmp_path):
    cimentacion = [("REFUERZO :", MARINA_REFUERZO)]  # traslape hasta #6, suelda desde #8
    plantas = [("REFUERZO :", MARINA_PB_REFUERZO)]  # traslape hasta #8, suelda desde #10
    entidades = _dibujo(tmp_path, bloques=[(cimentacion, 2), (plantas, 3)])
    r = leer_reglas(entidades, frames=_marcos_de_los_bloques())
    assert r.traslape_max_numero.valor == "8" and r.soldar_desde_numero.valor == "10"  # global

    de_cimentacion = r.para("ES-001")
    assert de_cimentacion.traslape_max_numero.valor == "6"
    assert de_cimentacion.soldar_desde_numero.valor == "8"
    assert de_cimentacion.traslape_max_numero.en_conflicto is False
    assert de_cimentacion.soldar_desde_numero.hoja == "ES-001"
    assert [a.valor for a in de_cimentacion.soldar_desde_numero.alternativas] == ["10"]

    de_plantas = r.para("ES-102")
    assert (
        de_plantas.traslape_max_numero.valor == "8" and de_plantas.soldar_desde_numero.valor == "10"
    )
    assert de_plantas.soldar_desde_numero.en_conflicto is False

    sin_copia = r.para("ES-999")
    assert (
        sin_copia.traslape_max_numero.valor == "8" and sin_copia.soldar_desde_numero.valor == "10"
    )
    assert sin_copia.traslape_max_numero.en_conflicto is True  # global, con su conflicto a la vista
    assert sin_copia.soldar_desde_numero.en_conflicto is True

    # Las reglas que no cambian de hoja a hoja son las mismas; la contradicción sigue a la vista.
    assert de_cimentacion.gancho_estribo.valor == r.gancho_estribo.valor
    assert de_cimentacion.primer_estribo_m["trabe"].valor == 0.06
    assert de_cimentacion.contradicciones == r.contradicciones and r.contradicciones
    assert de_cimentacion.avisos == r.avisos


def test_two_sheets_with_different_limits_resolve_each_its_own(tmp_path):
    """El caso del ruling: ES-000 traslapa hasta el #6 y suelda desde el #8; ES-100 hasta el #8 y
    desde el #10; ES-999 no dice nada y se queda con el conflicto a la vista."""
    from klave_engine.detection.frames import SheetFrame

    entidades = _dibujo(
        tmp_path,
        bloques=[
            ([("REFUERZO :", MARINA_REFUERZO)], 1),
            ([("REFUERZO :", MARINA_PB_REFUERZO)], 1),
        ],
    )
    marcos = [
        SheetFrame(frame_id="a", bbox=(40, 10, 140, 60), source_file="marina.dxf", code="ES-000"),
        SheetFrame(frame_id="b", bbox=(40, -60, 140, -10), source_file="marina.dxf", code="ES-100"),
    ]
    r = leer_reglas(entidades, frames=marcos)
    assert r.soldar_desde_numero.en_conflicto and r.traslape_max_numero.en_conflicto
    cimentacion, plantas, ninguna = r.para("ES-000"), r.para("ES-100"), r.para("ES-999")
    assert (cimentacion.traslape_max_numero.valor, cimentacion.soldar_desde_numero.valor) == (
        "6",
        "8",
    )
    assert (plantas.traslape_max_numero.valor, plantas.soldar_desde_numero.valor) == ("8", "10")
    assert not cimentacion.soldar_desde_numero.en_conflicto
    assert not plantas.soldar_desde_numero.en_conflicto
    # Una hoja sin copia propia se queda con la elegida entre todas, y su conflicto se ve.
    assert ninguna.soldar_desde_numero.valor == r.soldar_desde_numero.valor
    assert ninguna.soldar_desde_numero.en_conflicto is True
    assert ninguna.traslape_max_numero.en_conflicto is True


def test_para_does_not_change_the_reglas_it_was_called_on(tmp_path):
    cimentacion = [("REFUERZO :", MARINA_REFUERZO)]
    plantas = [("REFUERZO :", MARINA_PB_REFUERZO)]
    r = leer_reglas(
        _dibujo(tmp_path, bloques=[(cimentacion, 2), (plantas, 3)]), frames=_marcos_de_los_bloques()
    )
    antes = r.model_dump()
    r.para("ES-001")
    assert r.model_dump() == antes


def test_a_supuesto_is_the_same_for_every_sheet_in_para():
    r = reglas_estandar()
    de_una = r.para("ES-001")
    assert de_una.model_dump() == r.model_dump()


def test_para_survives_a_trip_through_json(tmp_path):
    import json

    cimentacion = [("REFUERZO :", MARINA_REFUERZO)]
    plantas = [("REFUERZO :", MARINA_PB_REFUERZO)]
    r = leer_reglas(
        _dibujo(tmp_path, bloques=[(cimentacion, 2), (plantas, 3)]), frames=_marcos_de_los_bloques()
    )
    vuelta = Reglas.model_validate(json.loads(json.dumps(r.model_dump(mode="json"))))
    assert vuelta.para("ES-001").soldar_desde_numero.valor == "8"
    assert vuelta.para("ES-101").soldar_desde_numero.valor == "10"
    assert vuelta.para("ES-999").soldar_desde_numero.en_conflicto is True


def test_the_table_of_a_sheet_keeps_the_bars_filled_from_the_standard(tmp_path):
    r = leer_reglas(_dibujo(tmp_path, tabla_kw={"sin": ("4",)}), frames=[])
    de_hoja = r.para("marina.dxf")
    assert de_hoja.tabla_varillas.valor["4"] == TABLA_ESTANDAR["4"]
    assert de_hoja.tabla_varillas.en_conflicto is False


def test_two_copies_of_the_table_that_differ_resolve_per_sheet(tmp_path):
    doc = ezdxf.new("R2010")
    _bloque(doc, "A")
    _bloque(doc, "B", cambio={("8", "LT1"): 120})
    msp = doc.modelspace()
    msp.add_blockref("A", (0.0, 0.0))
    msp.add_blockref("B", (40.0, 0.0))
    ruta = tmp_path / "dos.dxf"
    doc.saveas(ruta)
    entidades = DxfParser().parse_file(ruta).entities
    from klave_engine.detection.frames import SheetFrame

    marcos = [
        SheetFrame(frame_id="a", bbox=(-5, -5, 20, 5), source_file="dos.dxf", code="ES-001"),
        SheetFrame(frame_id="b", bbox=(30, -5, 60, 5), source_file="dos.dxf", code="ES-002"),
    ]
    r = leer_reglas(entidades, frames=marcos)
    assert r.tabla_varillas.en_conflicto is True
    assert r.para("ES-001").tabla_varillas.valor["8"].LT1 == 115
    assert r.para("ES-002").tabla_varillas.valor["8"].LT1 == 120
    assert r.para("ES-002").tabla_varillas.en_conflicto is False


def test_the_missing_bars_are_filled_in_every_copy_of_a_table_that_differs(tmp_path):
    doc = ezdxf.new("R2010")
    _bloque(doc, "A", sin=("4",))
    _bloque(doc, "B", sin=("4",), cambio={("8", "LT1"): 120})
    msp = doc.modelspace()
    msp.add_blockref("A", (0.0, 0.0))
    msp.add_blockref("B", (40.0, 0.0))
    ruta = tmp_path / "dos.dxf"
    doc.saveas(ruta)
    from klave_engine.detection.frames import SheetFrame

    marcos = [
        SheetFrame(frame_id="a", bbox=(-5, -5, 20, 5), source_file="dos.dxf", code="ES-001"),
        SheetFrame(frame_id="b", bbox=(30, -5, 60, 5), source_file="dos.dxf", code="ES-002"),
    ]
    r = leer_reglas(DxfParser().parse_file(ruta).entities, frames=marcos)
    for hoja, lt1 in (("ES-001", 115), ("ES-002", 120)):
        de_hoja = r.para(hoja).tabla_varillas
        assert de_hoja.valor["4"] == TABLA_ESTANDAR["4"] and de_hoja.valor["8"].LT1 == lt1
        assert de_hoja.en_conflicto is False  # la fila de la estándar no inventa una diferencia


# --- el texto que dice una regla de otra manera se lee, y si no se lee se avisa ------------------


@pytest.mark.parametrize(
    ("texto", "traslape", "soldar"),
    [
        (
            "SE PERMITE TRASLAPAR HASTA EL No. 6, DEL No. 8 Y DIAMETROS MAYORES SE SOLDARAN",
            "6",
            "8",
        ),
        (
            "SE PERMITE TRASLAPAR VARILLA HASTA EL #6. VARILLAS DEL #8 EN ADELANTE SE SOLDARÁN",
            "6",
            "8",
        ),
        ("EL TRASLAPE MAXIMO SERA CON VARILLAS DEL 6", "6", None),
        ("SE PERMITE TRASLAPAR VARILLAS HASTA EL 5, DEL 6 Y MAYORES SE SOLDARAN", "5", "6"),
        ("SE TRASLAPARA HASTA #6; A PARTIR DEL #8 SE SOLDARAN LAS VARILLAS", "6", "8"),
        ("SOLO SE PERMITE TRASLAPAR VARILLA HASTA EL #5 Y DESDE LA No. 6 SE SOLDARA", "5", "6"),
        ("LAS VARILLAS DEL #10 EN ADELANTE SE SOLDARAN, SIN TRASLAPES", None, "10"),
    ],
)
def test_lap_and_weld_phrasings_are_read(tmp_path, texto, traslape, soldar):
    r = _con_notas(tmp_path, [f"4. {texto}"])
    assert (r.traslape_max_numero and r.traslape_max_numero.valor) == (traslape or None)
    assert (r.soldar_desde_numero and r.soldar_desde_numero.valor) == (soldar or None)
    assert r.avisos == [], r.avisos  # lo que se lee no deja avisos


@pytest.mark.parametrize(
    ("texto", "tema"),
    [
        ("NO SE TRASLAPARA VARILLA MAYOR AL #6", "hasta qué varilla se traslapa"),
        ("LAS VARILLAS MAYORES AL #8 SE SOLDARAN A TOPE", "desde qué varilla se suelda"),
        ("EN TRABES EL PRIMER ESTRIBO IRA A 0.06 M DEL PAÑO", "el primer estribo"),
        ("LOS GANCHOS DE ESTRIBOS SERAN DE 135 GRADOS", "los ganchos de estribos y grapas"),
        ("PLANTILLA ESP=5 CM CON CONCRETO POBRE", "el espesor de la plantilla"),
    ],
)
def test_a_rule_a_note_names_with_a_number_and_that_is_not_read_is_reported(tmp_path, texto, tema):
    r = _con_notas(tmp_path, [f"4. {texto}"])
    (aviso,) = r.avisos
    assert tema in aviso and "La nota 4 de REFUERZO" in aviso and "no se usa" in aviso
    assert "«" in aviso  # cita lo que no entendió


def test_a_half_read_pair_says_which_half_is_missing(tmp_path):
    """R40: la mitad que no se lee es parte de la nota; la nota no se usa, y el aviso dice las dos
    reglas y qué no se leyó (antes se usaba la mitad leída y se avisaba de la otra)."""
    r = _con_notas(
        tmp_path,
        ["4. SE PERMITE TRASLAPAR VARILLA HASTA EL #6. LAS DE MAS DE LA No. 8 SE SOLDARAN"],
    )
    assert r.traslape_max_numero is None and r.soldar_desde_numero is None
    (aviso,) = r.avisos
    assert "hasta qué varilla se traslapa" in aviso and "desde qué varilla se suelda" in aviso
    assert "«LAS DE MAS DE LA No. 8 SE SOLDARAN»" in aviso and "no se usa nada" in aviso


def test_the_other_half_missing_is_reported_too(tmp_path):
    """R40: la cláusula negada que no se lee es parte de la nota: no se usa la que sí se leyó."""
    r = _con_notas(
        tmp_path,
        ["4. NO SE TRASLAPARA VARILLA MAYOR AL #6, DEL #8 Y DIAMETROS MAYORES SE SOLDARAN"],
    )
    assert r.soldar_desde_numero is None and r.traslape_max_numero is None
    (aviso,) = r.avisos
    assert "desde qué varilla se suelda" in aviso and "hasta qué varilla se traslapa" in aviso
    assert "«NO SE TRASLAPARA VARILLA MAYOR AL #6»" in aviso


def test_a_single_angle_hook_is_read_for_the_element_it_names(tmp_path):
    r = _con_notas(tmp_path, ["7. LOS ESTRIBOS TENDRAN GANCHOS A 135 GRADOS CON TRAMO RECTO DE 8Ø"])
    assert r.gancho_estribo.valor == {"angulo": 135, "recto_diametros": 8}
    assert r.gancho_estribo.fuente == "nota" and r.gancho_grapa.fuente == "supuesto"
    assert r.avisos == []


def test_a_single_angle_hook_without_the_straight_leg_says_so(tmp_path):
    r = _con_notas(tmp_path, ["7. LOS ESTRIBOS TENDRAN GANCHOS A 135 GRADOS"])
    assert r.gancho_estribo.valor == {"angulo": 135, "recto_diametros": 10}
    assert r.gancho_estribo.fuente == "nota"
    assert any("tramo recto" in a for a in r.avisos)


def test_a_single_angle_hook_for_stirrups_and_grapas_both_is_reported_not_guessed(tmp_path):
    r = _con_notas(tmp_path, ["7. LOS ESTRIBOS Y LAS GRAPAS TENDRAN GANCHOS A 135 GRADOS"])
    assert r.gancho_estribo.fuente == "supuesto" and r.gancho_grapa.fuente == "supuesto"
    assert any("estribos o de grapas" in a for a in r.avisos)


def test_cover_for_walls_of_containment_is_read_as_concrete_walls(tmp_path):
    renglones = ["4. EL RECUBRIMIENTO MINIMO SERA 5.0 CM EN CIMENTACION Y MUROS DE CONTENCION"]
    r = _con_notas(tmp_path, renglones, titulo="NOTAS :")
    assert r.recubrimiento_m["muro_concreto"].valor == 0.05
    assert r.recubrimiento_m["muro_concreto"].fuente == "nota"
    assert r.recubrimiento_m["zapata"].valor == 0.05 and r.avisos == []


def test_an_element_in_a_cover_list_that_nobody_recognises_is_reported(tmp_path):
    renglones = ["4. EL RECUBRIMIENTO MINIMO SERA 5.0 CM EN CIMENTACION Y ALBERCAS"]
    r = _con_notas(tmp_path, renglones, titulo="NOTAS :")
    assert r.recubrimiento_m["zapata"].valor == 0.05  # lo que sí se reconoce se usa
    (aviso,) = r.avisos
    assert "ALBERCAS" in aviso and "no se reconoce" in aviso


def test_a_rule_in_a_displaced_line_of_a_note_is_reported_not_lost(tmp_path):
    """La última línea de la nota quedó 2 unidades a la derecha (> 4 alturas): no es parte de la
    nota, y es la que trae el traslape y la soldadura."""
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for y, texto, dx in (
        (10.0, "4. NO SE PERMITIRA TRASLAPAR NI SOLDAR MAS DEL 50% DEL REFUERZO", 0.0),
        (9.78, "EN UNA MISMA SECCION, UNICAMENTE SE PERMITIRA TRASLAPAR VARILLA", 0.0),
        (9.56, "HASTA EL #6, DEL #8 Y DIAMETROS MAYORES SE SOLDARAN", 2.0),
    ):
        msp.add_text(texto, height=0.1).set_placement((dx, y))
    ruta = tmp_path / "corrida.dxf"
    doc.saveas(ruta)
    r = leer_reglas(DxfParser().parse_file(ruta).entities, frames=[])
    assert r.traslape_max_numero is None and r.soldar_desde_numero is None
    (aviso,) = r.avisos
    assert "SOLDARAN" in aviso and "no es una nota numerada" in aviso
    assert "corrida.dxf" in aviso  # dice dónde está


def test_a_multi_line_text_that_states_a_rule_is_reported_not_skipped(tmp_path):
    mtext = (
        "4.- NO SE PERMITIRA TRASLAPAR VARILLA HASTA EL #6\\PDEL #8 Y DIAMETROS MAYORES SE SOLDARAN"
    )
    r = leer_reglas(_dibujo(tmp_path, tabla=False, mtexts=[(mtext, 5.0, 5.0)]), frames=[])
    assert r.traslape_max_numero is None and r.soldar_desde_numero is None
    assert len(r.avisos) == 2
    assert any("hasta qué varilla se traslapa" in a for a in r.avisos)
    assert any("desde qué varilla se suelda" in a for a in r.avisos)
    assert all("no es una nota numerada" in a for a in r.avisos)


def test_the_same_unread_text_in_many_sheets_is_one_aviso_with_its_sheets(tmp_path):
    mtexts = [("PRIMER ESTRIBO A 0.06 M\\PEN TRABES", 5.0 + 100.0 * i, 5.0) for i in range(6)]
    from klave_engine.detection.frames import SheetFrame

    marcos = [
        SheetFrame(
            frame_id=f"f{i}",
            bbox=(100.0 * i, 0, 100.0 * i + 90, 20),
            source_file="marina.dxf",
            code=f"ES-00{i}",
        )
        for i in range(6)
    ]
    r = leer_reglas(_dibujo(tmp_path, tabla=False, mtexts=mtexts), frames=marcos)
    (aviso,) = r.avisos
    assert "el primer estribo" in aviso and "ES-000, ES-001, ES-002 y 3 hojas más" in aviso


def test_a_plantilla_text_with_only_its_strength_is_not_a_missing_thickness(tmp_path):
    textos = [("PLANTILLA DE CONCRETO F'C=100 KG/CM2", 5.0, 5.0)]
    r = leer_reglas(_dibujo(tmp_path, tabla=False, mtexts=textos), frames=[])
    assert r.plantilla_espesor_m is None and r.avisos == []


def test_a_plantilla_with_a_thickness_nobody_reads_is_reported(tmp_path):
    r = leer_reglas(
        _dibujo(tmp_path, tabla=False, mtexts=[("PLANTILLA ESP=5 CM", 5.0, 5.0)]), frames=[]
    )
    assert r.plantilla_espesor_m is None
    (aviso,) = r.avisos
    assert "el espesor de la plantilla" in aviso and "no se pudo leer" in aviso


MARINA_REFUERZO_COMPLETO = [
    "1. EN TRABES NO SE DEBERA SOLDAR O ACOPLAR MAS DEL 50 %%% DEL",
    "REFUERZO LONGITUDINAL EN UNA SOLA SECCION, LA DISTANCIA ENTRE",
    "SECCIONES DONDE SE REALICEN TRASLAPES NO SERA MENOR A 40 VECES",
    "EL DIAMETRO DE LA BARRA MAS GRUESA.",
    "2. NO DEBERAN EFECTUARSE TRASLAPES DENTRO DE LOS NUDOS, NI EN UNA",
    "DISTANCIA DE DOS PERALTES MEDIDA A PARTIR DEL PAÑO DEL NUDO.",
    *MARINA_REFUERZO[:2],
    *MARINA_REFUERZO[2:6],
    "5. LAS LONGITUDES DE ANCLAJE RECTO Y TRASLAPE PARA VARILLAS",
    "CORRUGADAS SE ESPECIFICAN EN LA TABLA No. 1.",
    "6. SI NO SE HACE OTRA INDICACION, TODAS LAS VARILLAS TERMINADAS EN",
    "ESCUADRAS SE ANCLARAN EN LOS ELEMENTOS NORMALES COMO SE",
    "INDICA EN LA FIGURA A.",
    *MARINA_REFUERZO[6:],
    "8. EN LA FIG-C SE REPRESENTA LA LONGITUD DE TRASLAPE.",
]


def test_marinas_own_notes_about_welds_and_laps_that_state_no_limit_stay_silent(tmp_path):
    """Las notas 1, 2, 5, 6 y 8 de REFUERZO hablan de traslapes y soldadura sin dar un límite de
    varilla (50 %, «TABLA No. 1», 40 diámetros): no son una regla que se dejó de leer."""
    r = _con_notas(tmp_path, MARINA_REFUERZO_COMPLETO)
    assert r.traslape_max_numero.valor == "6" and r.soldar_desde_numero.valor == "8"
    assert r.primer_estribo_m["trabe"].valor == 0.06
    assert r.gancho_estribo.fuente == "nota"
    assert r.avisos == []


def test_a_table_reference_is_not_a_bar_number(tmp_path):
    r = _con_notas(
        tmp_path, ["5. EL TRASLAPE MAXIMO Y EL ANCLAJE SE ESPECIFICAN EN LA TABLA No. 1."]
    )
    assert r.traslape_max_numero is None and r.avisos == []


def test_a_percentage_is_not_a_bar_number(tmp_path):
    renglones = [
        "1. NO SE DEBERA SOLDAR MAS DEL 50 % DEL REFUERZO",
        "NI TRASLAPAR VARILLA MAYOR A LA DEL PROYECTO",
    ]
    r = _con_notas(tmp_path, renglones)
    assert r.soldar_desde_numero is None and r.avisos == []


def test_a_materials_text_that_mentions_bars_from_a_number_on_is_no_weld_rule(tmp_path):
    # «… VARILLAS DEL No.3 EN ADELANTE …» en la nota de materiales no es una regla de soldadura ni
    # un aviso: es el fy de las varillas (R119), y se lee.
    mtext = (
        "2.\\t ACERO DE REFUERZO CON F'Y=4200KG/CM2 EN VARILLAS DEL No.3\\PEN ADELANTE Y "
        "F'Y=2530KG/CM2 EN VARILLAS DEL No.2."
    )
    r = leer_reglas(_dibujo(tmp_path, tabla=False, mtexts=[(mtext, 5.0, 5.0)]), frames=[])
    assert r.avisos == [] and r.soldar_desde_numero is None and r.fy_kg_cm2["3"].valor == 4200


# --- los arreglos menores ---------------------------------------------------------------------


def test_the_conflict_sentence_lists_only_the_readings_of_the_deciding_rank(tmp_path):
    notas = [("NOTAS :", ["2. BAJO LA CIMENTACION SE COLOCARA PLANTILLA DE 4 CM"])]
    mtexts = [("PLANTILLA 5 CM", 5.0, 5.0), ("PLANTILLA 6 CM", 15.0, 5.0)]
    r = leer_reglas(_dibujo(tmp_path, tabla=False, bloques=[(notas, 1)], mtexts=mtexts), frames=[])
    assert r.plantilla_espesor_m.fuente == "detalle" and r.plantilla_espesor_m.en_conflicto
    (frase,) = [c for c in r.contradicciones if "plantilla" in c]
    assert "5 cm" in frase and "6 cm" in frase
    assert "4 cm" not in frase  # la nota quedó por debajo de los detalles: no decide
    assert [a.valor for a in r.plantilla_espesor_m.alternativas if a.fuente == "nota"] == [0.04]


def test_the_same_value_twice_in_one_note_counts_one_copy(tmp_path):
    renglones = ["4. EL RECUBRIMIENTO MINIMO SERA 5.0 CM EN TRABES Y TAMBIEN 5.0 CM EN TRABES"]
    r = leer_reglas(
        _dibujo(tmp_path, tabla=False, bloques=[([("NOTAS :", renglones)], 3)]), frames=[]
    )
    assert r.recubrimiento_m["trabe"].copias == 3  # tres copias del bloque, no seis
    assert len(r.recubrimiento_m["trabe"].alternativas) == 0


def test_the_same_value_in_two_different_notes_counts_both(tmp_path):
    renglones = [
        "4. EL RECUBRIMIENTO MINIMO SERA 5.0 CM EN COLUMNAS",
        # R40: «DE LAS COLUMNAS DE ORILLA» acotaría la nota; otra redacción que no acota.
        "5. EL RECUBRIMIENTO LIBRE DE LAS VARILLAS SERA 5.0 CM EN COLUMNAS",
    ]
    r = leer_reglas(
        _dibujo(tmp_path, tabla=False, bloques=[([("NOTAS :", renglones)], 1)]), frames=[]
    )
    assert (
        r.recubrimiento_m["columna"].copias == 2 and not r.recubrimiento_m["columna"].en_conflicto
    )


def test_the_table_says_which_bars_it_has_no_row_for(tmp_path):
    r = leer_reglas(_dibujo(tmp_path), frames=[])
    assert "sin fila para #2 y #7: ni el plano ni la estándar las traen" in r.tabla_varillas.texto
    assert r.avisos == []  # un dato del texto, no un aviso por proyecto
    estandar = reglas_estandar().tabla_varillas
    assert "sin fila para #2 y #7: la estándar no las trae" in estandar.texto
    completa = leer_reglas(_dibujo(tmp_path, tabla_kw={"sin": ("4",)}), frames=[]).tabla_varillas
    assert "#4 de la tabla estándar (supuesto)" in completa.texto
    assert "sin fila para #2 y #7" in completa.texto


# --- ronda 2: números pelados, ganchos de otra oración, plantilla en metros, rangos -------------


@pytest.mark.parametrize(
    ("texto", "traslape", "soldar"),
    [
        ('SE PERMITE TRASLAPAR VARILLAS HASTA 3/4"', "6", None),
        ('SE PERMITE TRASLAPAR VARILLAS HASTA EL 1"', "8", None),
        ('SE PERMITE TRASLAPAR VARILLAS HASTA 1 1/4"', "10", None),
        ('SE PERMITE TRASLAPAR VARILLA HASTA EL #5 Y DEL 3/4" EN ADELANTE SE SOLDARAN', "5", "6"),
        ("SE PERMITE TRASLAPAR VARILLA HASTA EL NUMERO 6", "6", None),
        ("SE PERMITE TRASLAPAR VARILLA HASTA EL NUM. 6", "6", None),
        ("SE PERMITE TRASLAPAR VARILLAS DEL No. 3 AL No. 6", "6", None),
        ("SE PERMITE TRASLAPAR VARILLAS DEL #3 A LA #5", "5", None),
        ("LAS VARILLAS DEL No. 7 AL No. 12 SE SOLDARAN", None, "7"),
        ("SE SOLDARAN LAS VARILLAS DEL No. 7 AL No. 12", None, "7"),
        ("LA SOLDADURA SE USARA EN VARILLAS DEL No. 8 EN ADELANTE", None, "8"),
    ],
)
def test_more_ways_of_writing_a_bar_are_read(tmp_path, texto, traslape, soldar):
    r = _con_notas(tmp_path, [f"4. {texto}"])
    assert (r.traslape_max_numero and r.traslape_max_numero.valor) == traslape
    assert (r.soldar_desde_numero and r.soldar_desde_numero.valor) == soldar
    assert r.avisos == [], r.avisos


def test_a_lap_limit_without_a_verb_is_reported_not_read(tmp_path):
    """R39: «LOS TRASLAPES HASTA VARILLA 6» no tiene verbo, y lo que le falta puede negarlo («LOS
    TRASLAPES HASTA EL #6 NO SE PERMITEN EN COLUMNAS»): no se lee sola, se avisa."""
    r = _con_notas(tmp_path, ["4. LOS TRASLAPES HASTA VARILLA 6"])
    assert r.traslape_max_numero is None
    (aviso,) = r.avisos
    assert "hasta qué varilla se traslapa" in aviso and "«LOS TRASLAPES HASTA VARILLA 6»" in aviso


@pytest.mark.parametrize(
    "texto",
    [
        "NO SE PERMITIRA TRASLAPAR HASTA 2 VARILLAS POR SECCION",
        "SE PERMITE TRASLAPAR HASTA 2 BARRAS POR SECCION",
        "SE PERMITE TRASLAPAR HASTA 50% DE LAS VARILLAS EN UNA SECCION",
        "SE PERMITE TRASLAPAR HASTA 40 VECES EL DIAMETRO",
    ],
)
def test_a_bare_number_that_counts_something_else_is_not_a_bar(tmp_path, texto):
    r = _con_notas(tmp_path, [f"4. {texto}"])
    assert r.traslape_max_numero is None and r.soldar_desde_numero is None
    assert r.avisos == []  # no fija un límite de varilla: no hay nada que se haya dejado de leer


def test_an_inch_fraction_that_is_not_a_bar_is_reported(tmp_path):
    r = _con_notas(tmp_path, ['4. SE PERMITE TRASLAPAR VARILLAS HASTA 3/16"'])
    assert r.traslape_max_numero is None
    assert any('«3/16"»' in a and "no es un número de varilla" in a for a in r.avisos)


@pytest.mark.parametrize(
    "texto",
    [
        "NO SE TRASLAPARA VARILLA 6 O MAYOR",
        "NO SE TRASLAPARA VARILLA MAYOR AL NUMERO 6",
        "NO SE TRASLAPARA VARILLA MAYOR AL NUM. 6",
        'NO SE TRASLAPARA VARILLA MAYOR AL 3/4"',
        "NO SE TRASLAPARA VARILLA MAYOR A 5/8 PULG",
    ],
)
def test_other_ways_of_naming_a_bar_make_an_unread_limit_visible(tmp_path, texto):
    r = _con_notas(tmp_path, [f"4. {texto}"])
    assert r.traslape_max_numero is None
    (aviso,) = r.avisos
    assert "hasta qué varilla se traslapa" in aviso and "no se pudo leer" in aviso


def test_a_weld_range_that_stops_short_of_the_biggest_bar_is_reported_not_guessed(tmp_path):
    r = _con_notas(tmp_path, ["4. LAS VARILLAS DEL No. 7 AL No. 10 SE SOLDARAN"])
    assert r.soldar_desde_numero is None  # no dice qué pasa con la #12
    (aviso,) = r.avisos
    assert "desde qué varilla se suelda" in aviso and "no se pudo leer" in aviso


def test_a_weld_sentence_with_soldadura_that_is_not_read_is_reported(tmp_path):
    r = _con_notas(tmp_path, ["4. LA SOLDADURA SE APLICARA A PARTIR DE LA VARILLA No. 8"])
    assert r.soldar_desde_numero is None
    (aviso,) = r.avisos
    assert "desde qué varilla se suelda" in aviso and "No. 8" in aviso


def test_a_hook_of_the_next_sentence_is_not_the_stirrups_hook(tmp_path):
    texto = (
        "7. LOS ESTRIBOS SE COLOCARAN @ 10 CM. TODAS LAS ESCUADRAS LLEVARAN GANCHOS A 90° "
        "CON TRAMO RECTO DE 12Ø"
    )
    r = _con_notas(tmp_path, [texto])
    assert r.gancho_estribo.fuente == "supuesto" and r.gancho_grapa.fuente == "supuesto"
    assert r.gancho_estribo.valor == {"angulo": 135, "recto_diametros": 10}
    assert r.avisos == []  # un gancho de otras varillas no es una regla de estribos ni de grapas


def test_a_hook_of_other_bars_is_silent_even_with_stirrups_in_the_note(tmp_path):
    renglones = [
        "7. LAS VARILLAS TERMINADAS EN ESCUADRA LLEVARAN UN GANCHO DE 90° COMO SE INDICA.",
        "LOS ESTRIBOS SE COLOCARAN CADA 15 CM.",
    ]
    r = _con_notas(tmp_path, renglones)
    assert r.gancho_estribo.fuente == "supuesto" and r.avisos == []


def test_a_sentence_with_a_numbered_bar_does_not_end_at_its_abbreviation(tmp_path):
    texto = "7. LOS ESTRIBOS DEL No. 3 TENDRAN GANCHOS A 135 GRADOS CON TRAMO RECTO DE 10Ø"
    r = _con_notas(tmp_path, [texto])
    assert r.gancho_estribo.valor == {"angulo": 135, "recto_diametros": 10}
    assert r.gancho_estribo.fuente == "nota" and r.avisos == []


def test_a_plantilla_measure_that_is_not_its_thickness_is_reported_not_read(tmp_path):
    for medida in ("0.10 M", "10 CM"):
        texto = f"PLANTILLA DE CONCRETO POBRE QUE SOBRESALDRA DE {medida}"
        r = leer_reglas(_dibujo(tmp_path, tabla=False, mtexts=[(texto, 5.0, 5.0)]), frames=[])
        assert r.plantilla_espesor_m is None, medida
        (aviso,) = r.avisos
        assert "el espesor de la plantilla" in aviso and "no se pudo leer" in aviso


@pytest.mark.parametrize(
    "texto",
    [
        "PLANTILLA DE 0.05 M DE ESPESOR",
        "PLANTILLA DE CONCRETO POBRE DE 0.05 M DE ESP.",
        "PLANTILLA DE CONCRETO POBRE, ESPESOR DE 0.05 MTS",
    ],
)
def test_a_plantilla_thickness_in_meters_is_read_when_it_says_so(tmp_path, texto):
    r = leer_reglas(_dibujo(tmp_path, tabla=False, mtexts=[(texto, 5.0, 5.0)]), frames=[])
    assert r.plantilla_espesor_m.valor == 0.05 and r.avisos == []


def test_marinas_steel_and_materials_texts_stay_silent_with_the_wider_triggers(tmp_path):
    mtexts = [
        (
            "2.- EXCEPTO DONDE SE INDIQUE OTRA COSA, TODOS LOS ELEMENTOS SE SOLDARAN CON "
            "ELECTRODOS E-70\\P3.- TODAS LAS SOLDADURAS SERAN EJECUTADAS POR OPERARIOS "
            'CALIFICADOS EN PLACAS DE 3/8" Y 1/2".',
            5.0,
            5.0,
        ),
        ('EL TAMAÑO MAXIMO DEL AGREGADO SERA 3/4"\\PVARILLAS DEL No.3 EN ADELANTE', 15.0, 5.0),
    ]
    r = leer_reglas(_dibujo(tmp_path, tabla=False, mtexts=mtexts), frames=[])
    assert r.avisos == []


def test_the_missing_rows_note_is_in_every_copy_of_the_table(tmp_path):
    doc = ezdxf.new("R2010")
    _bloque(doc, "A")
    _bloque(doc, "B", cambio={("8", "LT1"): 120})
    msp = doc.modelspace()
    msp.add_blockref("A", (0.0, 0.0))
    msp.add_blockref("B", (40.0, 0.0))
    ruta = tmp_path / "dos.dxf"
    doc.saveas(ruta)
    from klave_engine.detection.frames import SheetFrame

    marcos = [
        SheetFrame(frame_id="a", bbox=(-5, -5, 20, 5), source_file="dos.dxf", code="ES-001"),
        SheetFrame(frame_id="b", bbox=(30, -5, 60, 5), source_file="dos.dxf", code="ES-002"),
    ]
    r = leer_reglas(DxfParser().parse_file(ruta).entities, frames=marcos)
    for hoja in ("ES-001", "ES-002"):
        texto = r.para(hoja).tabla_varillas.texto
        assert "sin fila para #2 y #7: ni el plano ni la estándar las traen" in texto, hoja
    assert all("sin fila para #2 y #7" in a.texto for a in r.tabla_varillas.alternativas)


def test_para_hands_back_copies_even_for_a_sheet_without_a_copy_of_its_own(tmp_path):
    cimentacion = [("REFUERZO :", MARINA_REFUERZO)]
    plantas = [("REFUERZO :", MARINA_PB_REFUERZO)]
    r = leer_reglas(
        _dibujo(tmp_path, bloques=[(cimentacion, 2), (plantas, 3)]), frames=_marcos_de_los_bloques()
    )
    antes = r.model_dump()
    for hoja in ("ES-999", "ES-001"):
        de_hoja = r.para(hoja)
        de_hoja.avisos.append("x")
        de_hoja.contradicciones.clear()
        de_hoja.soldar_desde_numero.valor = "99"
        de_hoja.soldar_desde_numero.alternativas.clear()
        de_hoja.recubrimiento_m["zapata"].valor = 9.0
        de_hoja.primer_estribo_m["trabe"].texto = "x"
        de_hoja.tabla_varillas.valor["8"].LT1 = 1
        de_hoja.gancho_estribo.hojas.append("zzz")
        assert r.model_dump() == antes, hoja


def test_para_of_the_standard_reglas_is_a_copy_too():
    r = reglas_estandar()
    de_hoja = r.para("ES-001")
    de_hoja.recubrimiento_m["zapata"].valor = 9.0
    de_hoja.tabla_varillas.valor["8"].LT1 = 1
    assert r.recubrimiento_m["zapata"].valor == 0.05 and r.tabla_varillas.valor["8"].LT1 is None


# --- ronda 3: una regla se lee sólo de una frase conocida que la oración dice en positivo -------


def _frases(texto):
    return [texto[i:f] for i, f in oraciones(texto)]


def test_a_period_after_a_unit_or_an_abbreviation_does_not_end_the_sentence_before_a_connector():
    assert _frases("LOS ESTRIBOS SE COLOCARAN @ 15 CM. CON GANCHOS A 135°") == [
        "LOS ESTRIBOS SE COLOCARAN @ 15 CM. CON GANCHOS A 135°"
    ]
    for una_sola in (
        'ESTRIBOS Ø3/8" @ 15 CMS. CON GANCHO A 135°',
        "ESTRIBOS F'Y=4200 KG/CM2. CON GANCHOS A 135°",
        "LOS ESTRIBOS, VER FIG. 4, TENDRAN GANCHOS A 135°",
        "ESTRIBOS SEGUN ART. 5 CON GANCHOS A 135°",
        "ESTRIBOS Nº. 3 CON GANCHOS A 135°",
        "LOS ESTRIBOS DEL NO. 3 SE COLOCARAN @ 15CM. Y TENDRAN GANCHOS",
        "PLANTILLA 5 CM DE ESP. DE CONCRETO F'C=100",
    ):
        assert _frases(una_sola) == [una_sola], una_sola


def test_a_period_after_a_unit_before_a_new_sentence_still_ends_it():
    texto = "LOS ESTRIBOS SE COLOCARAN @ 10 CM. TODAS LAS ESCUADRAS LLEVARAN GANCHOS A 90°"
    assert _frases(texto) == [
        "LOS ESTRIBOS SE COLOCARAN @ 10 CM.",
        "TODAS LAS ESCUADRAS LLEVARAN GANCHOS A 90°",
    ]
    assert _frases("UNA COSA; OTRA COSA. Y UNA TERCERA") == [  # «COSA.» no es unidad ni abreviatura
        "UNA COSA;",
        "OTRA COSA.",
        "Y UNA TERCERA",
    ]
    assert _frases("EL ANGULO SERA 135°") == ["EL ANGULO SERA 135°"]
    assert _frases("") == [""]


def test_a_negation_cancels_the_phrase_of_its_own_clause_only():
    frase = "NO SE PERMITIRA TRASLAPAR NI SOLDAR MAS DEL 50 % DEL REFUERZO, SE TRASLAPA HASTA EL #6"
    desde = frase.index("HASTA")
    assert not niega(frase, desde, len(frase))  # la negación es de la cláusula anterior
    assert niega(frase, frase.index("TRASLAPAR"), frase.index("TRASLAPAR") + 9)
    assert niega("SIN SOLDADURA EN VARILLAS DEL No. 8", 4, 14)
    assert not niega("TRASLAPAR HASTA EL No. 6", 0, 24)  # «No.» no es una negación
    assert not niega("DE 2,5 CM NO", 0, 5)  # la coma de un decimal no corta la cláusula


_ESTRIBOS = "TRAMO RECTO DE 10Ø"


@pytest.mark.parametrize(
    "texto",
    [
        f"LOS ESTRIBOS DEL No. 3 SE COLOCARAN @ 15 CM. CON GANCHOS A 135° Y {_ESTRIBOS}",
        f'ESTRIBOS Ø3/8" @ 15 CMS. CON GANCHO A 135° Y {_ESTRIBOS}',
        f"ESTRIBOS F'Y=4200 KG/CM2. CON GANCHOS A 135° Y {_ESTRIBOS}",
        f"LOS ESTRIBOS, VER FIG. 4, TENDRAN GANCHOS A 135° Y {_ESTRIBOS}",
        f"ESTRIBOS SEGUN ART. 5 CON GANCHOS A 135° Y {_ESTRIBOS}",
        f"ESTRIBOS Nº. 3 CON GANCHOS A 135° Y {_ESTRIBOS}",
    ],
)
def test_stirrup_hooks_after_a_unit_or_abbreviation_period_are_read(tmp_path, texto):
    r = _con_notas(tmp_path, [f"7. {texto}"])
    assert r.gancho_estribo.valor == {"angulo": 135, "recto_diametros": 10}
    assert r.gancho_estribo.fuente == "nota" and r.avisos == []


def test_a_hook_whose_angle_is_in_the_next_sentence_is_reported(tmp_path):
    texto = "LOS ESTRIBOS LLEVARAN GANCHOS EN SUS EXTREMOS. EL ANGULO SERA 135°"
    r = _con_notas(tmp_path, [f"7. {texto}"])
    assert r.gancho_estribo.fuente == "supuesto"
    (aviso,) = r.avisos
    assert "los ganchos de estribos y grapas" in aviso and "no se pudo leer" in aviso


@pytest.mark.parametrize(
    "texto",
    [
        "NO SE TRASLAPARAN VARILLAS DEL No. 8 AL No. 12",
        "NO SE PERMITE TRASLAPAR VARILLAS DEL #8 AL #12",
        "NI SE TRASLAPARAN VARILLAS DEL No. 8 AL No. 12, SE SOLDARAN",
        "NO SE PERMITE TRASLAPAR VARILLA HASTA EL #6",
        "NUNCA SE TRASLAPARA VARILLA HASTA EL #6",
        "SE PROHIBE TRASLAPAR VARILLA HASTA EL #6",
    ],
)
def test_a_negated_lap_rule_is_never_read_and_is_reported(tmp_path, texto):
    r = _con_notas(tmp_path, [f"4. {texto}"])
    assert r.traslape_max_numero is None
    assert any("hasta qué varilla se traslapa" in a and "no se pudo leer" in a for a in r.avisos)


@pytest.mark.parametrize(
    "texto",
    [
        "LA SOLDADURA NO SE PERMITE EN VARILLAS DEL No. 8 EN ADELANTE",
        "NO SE PERMITE LA SOLDADURA EN VARILLAS DEL No. 8 EN ADELANTE",
        "SIN SOLDADURA EN VARILLAS DEL No. 8 EN ADELANTE",
        "NO SE SOLDARAN VARILLAS DEL No. 3 AL No. 12",
        "NO SE SOLDARAN LAS VARILLAS DEL #10 EN ADELANTE",
    ],
)
def test_a_negated_weld_rule_is_never_read_and_is_reported(tmp_path, texto):
    r = _con_notas(tmp_path, [f"4. {texto}"])
    assert r.soldar_desde_numero is None
    assert any("desde qué varilla se suelda" in a and "no se pudo leer" in a for a in r.avisos)


def test_a_negation_in_an_earlier_clause_does_not_cancel_the_next_clause(tmp_path):
    renglones = [
        "4. NO SE PERMITIRA TRASLAPAR NI SOLDAR MAS DEL 50% DEL REFUERZO EN UNA MISMA SECCION,",
        "UNICAMENTE SE PERMITIRA TRASLAPAR VARILLA HASTA EL #6, DEL #8 Y DIAMETROS",
        "MAYORES SE SOLDARAN",
    ]
    r = _con_notas(tmp_path, renglones)
    assert r.traslape_max_numero.valor == "6" and r.soldar_desde_numero.valor == "8"
    assert r.avisos == []


def test_the_same_negation_in_the_same_clause_cancels_the_weld_that_follows(tmp_path):
    r = _con_notas(
        tmp_path,
        ["4. NO SE TRASLAPARA VARILLA MAYOR AL #6 Y DEL #8 Y DIAMETROS MAYORES SE SOLDARAN"],
    )
    assert r.traslape_max_numero is None and r.soldar_desde_numero is None
    assert len(r.avisos) == 2


@pytest.mark.parametrize(
    "texto",
    [
        "SE PERMITE TRASLAPAR HASTA 1/2 DEL REFUERZO EN UNA SECCION",
        "SE PERMITE TRASLAPAR HASTA 3/4 DEL REFUERZO",
        "SE PERMITE TRASLAPAR VARILLAS HASTA 5/8",
        "LAS VARILLAS DEL 3/4 EN ADELANTE SE SOLDARAN",
    ],
)
def test_a_fraction_without_a_quote_is_not_an_inch_bar_and_is_reported(tmp_path, texto):
    r = _con_notas(tmp_path, [f"4. {texto}"])
    assert r.traslape_max_numero is None and r.soldar_desde_numero is None
    assert any("no se sabe si son pulgadas" in a for a in r.avisos)  # avisos: ver el ledger


@pytest.mark.parametrize(
    ("texto", "numero"),
    [('HASTA 3/4"', "6"), ("HASTA 3/4 PULG", "6"), ("HASTA 5/8 PULGADAS", "5"), ("HASTA 1''", "8")],
)
def test_a_fraction_with_a_quote_or_pulg_is_an_inch_bar(tmp_path, texto, numero):
    r = _con_notas(tmp_path, [f"4. SE PERMITE TRASLAPAR VARILLAS {texto}"])
    assert r.traslape_max_numero.valor == numero and r.avisos == []


@pytest.mark.parametrize(
    "texto",
    [
        "HASTA 2 POR SECCION",
        "HASTA 3 EN UNA MISMA SECCION",
        "HASTA 3 VARS. POR SECCION",
        "HASTA 4 REDONDOS",
        "HASTA 2 PIEZAS",
        "HASTA 3 EMPALMES",
        "HASTA 3 DE LAS 6 VARILLAS",
        "HASTA 3 DE CADA 6",
        "HASTA 10Ø",
    ],
)
def test_a_count_after_hasta_is_not_a_bar(tmp_path, texto):
    r = _con_notas(tmp_path, [f"4. SE PERMITE TRASLAPAR {texto}"])
    assert r.traslape_max_numero is None and r.avisos == []
    r = _con_notas(tmp_path, [f"4. LOS TRASLAPES {texto}"])
    assert r.traslape_max_numero is None and r.avisos == []


@pytest.mark.parametrize(
    ("texto", "traslape"),
    [
        ("HASTA EL 6", "6"),
        ("HASTA EL 6.", "6"),
        ("HASTA EL 6, INCLUSIVE", "6"),
        ("HASTA 6 INCLUSIVE", "6"),
        ("HASTA 6 O MENOR", "6"),
        ("HASTA 6 Y MENORES", "6"),
        ("HASTA EL 6)", "6"),
        ("HASTA EL 6; LAS DEMAS SE SOLDARAN", "6"),
    ],
)
def test_a_bare_bar_number_is_read_when_the_sentence_closes_it(tmp_path, texto, traslape):
    r = _con_notas(tmp_path, [f"4. SE PERMITE TRASLAPAR VARILLA {texto}"])
    assert r.traslape_max_numero.valor == traslape


def test_stirrups_and_grapas_with_their_own_angle_are_both_read(tmp_path):
    texto = f"7. LOS ESTRIBOS LLEVARAN GANCHOS A 135° Y LAS GRAPAS A 180° CON {_ESTRIBOS}"
    r = _con_notas(tmp_path, [texto])
    assert r.gancho_estribo.valor == {"angulo": 135, "recto_diametros": 10}
    assert r.gancho_grapa.valor == {"angulo": 180, "recto_diametros": 10}
    assert r.gancho_estribo.fuente == r.gancho_grapa.fuente == "nota" and r.avisos == []


def test_a_second_hook_in_the_same_sentence_that_no_phrase_reads_is_reported(tmp_path):
    """R40: la parte que no se lee («LAS GRAPAS TENDRAN 180°…») es de la misma nota: no se usa
    ningún gancho de ella, y el aviso dice cuál parte no se leyó."""
    texto = f"7. LOS ESTRIBOS LLEVARAN GANCHOS A 135° Y LAS GRAPAS TENDRAN 180° CON {_ESTRIBOS}"
    r = _con_notas(tmp_path, [texto])
    assert r.gancho_estribo.fuente == "supuesto" and r.gancho_grapa.fuente == "supuesto"
    (aviso,) = r.avisos
    assert "«LAS GRAPAS TENDRAN 180° CON TRAMO RECTO DE 10Ø»" in aviso


@pytest.mark.parametrize(
    "texto",
    [
        "PLANTILLA DE 0.10 M DE ANCHO",
        "PLANTILLA DE 10 CM DE VOLADO",
        "PLANTILLA DE 10 CM MAS DE CADA LADO",
        "PLANTILLA DE 10 CM POR LADO",
        "PLANTILLA DE 10 CM SOBRE LA ZAPATA",
    ],
)
def test_a_plantilla_measure_followed_by_something_else_is_not_the_thickness(tmp_path, texto):
    r = leer_reglas(_dibujo(tmp_path, tabla=False, mtexts=[(texto, 5.0, 5.0)]), frames=[])
    assert r.plantilla_espesor_m is None
    (aviso,) = r.avisos
    assert "el espesor de la plantilla" in aviso and "no se pudo leer" in aviso


def test_a_plantilla_with_its_thickness_and_its_overhang_reads_the_thickness(tmp_path):
    texto = "PLANTILLA DE 10 CM DE VOLADO Y 5 CM DE ESPESOR"
    r = leer_reglas(_dibujo(tmp_path, tabla=False, mtexts=[(texto, 5.0, 5.0)]), frames=[])
    assert r.plantilla_espesor_m.valor == 0.05 and r.avisos == []


def test_a_negated_plantilla_is_not_read(tmp_path):
    r = leer_reglas(
        _dibujo(tmp_path, tabla=False, mtexts=[("SIN PLANTILLA DE 5 CM", 5.0, 5.0)]), frames=[]
    )
    assert r.plantilla_espesor_m is None and len(r.avisos) == 1


def test_a_negated_first_stirrup_is_not_read_and_a_negated_hook_neither(tmp_path):
    r = _con_notas(tmp_path, ["3. EN TRABES NO SE COLOCARA EL PRIMER ESTRIBO A 6 CMS."])
    assert r.primer_estribo_m == {}
    assert any("el primer estribo" in a and "no se pudo leer" in a for a in r.avisos)
    r = _con_notas(tmp_path, ["7. LOS ESTRIBOS NO LLEVARAN GANCHOS A 135°"])
    assert r.gancho_estribo.fuente == "supuesto"
    assert any("los ganchos de estribos y grapas" in a for a in r.avisos)


@pytest.mark.parametrize(
    "texto",
    [
        "LAS VARILLAS DEL #8 EN ADELANTE SE SOLDARAN A TOPE. NO SE TRASLAPARAN",
        "SE SOLDARAN LAS VARILLAS DEL No. 8 EN ADELANTE, NO SE PERMITEN TRASLAPES",
        "LAS VARILLAS DEL #8 EN ADELANTE SE SOLDARAN, SIN TRASLAPES",
    ],
)
def test_a_negation_that_only_repeats_what_was_read_is_not_a_missing_half(tmp_path, texto):
    r = _con_notas(tmp_path, [f"4. {texto}"])
    assert r.soldar_desde_numero.valor == "8" and r.traslape_max_numero is None
    assert r.avisos == []


def test_the_whole_note_is_looked_at_not_just_the_window_around_the_keyword(tmp_path):
    relleno = "LA SEPARACION SE MIDE DESDE EL PAÑO DE LOS APOYOS EN TODOS LOS CASOS. " * 4
    r = _con_notas(tmp_path, [f"7. LOS ESTRIBOS LLEVARAN GANCHOS EN SUS EXTREMOS. {relleno}"])
    assert not any("ganchos" in a for a in r.avisos)  # sin ángulo en ningún lado: nada que leer
    r = _con_notas(
        tmp_path, [f"7. LOS ESTRIBOS LLEVARAN GANCHOS EN SUS EXTREMOS. {relleno}ANGULO 135°"]
    )
    assert any("los ganchos de estribos y grapas" in a for a in r.avisos)


def test_the_families_of_a_first_stirrup_are_those_of_its_own_sentence(tmp_path):
    texto = "3. EN COLUMNAS SE USARAN ESTRIBOS CERRADOS. EL PRIMER ESTRIBO IRA A 6 CMS DEL PAÑO."
    r = _con_notas(tmp_path, [texto])
    assert r.primer_estribo_m == {}  # «EN COLUMNAS» es de la oración de antes
    assert any("el primer estribo" in a.lower() and "no dice" in a for a in r.avisos)


# --- ronda 4 (R39): una regla se lee sólo si una frase conocida cubre su cláusula entera -------
#
# Cada caso dice lo único que vale: la lectura correcta, o ninguna lectura (y, si el texto nombra
# la regla con un número, un aviso). Un valor equivocado nunca.


def _sin_lectura(r, campo):
    """``True`` si ``campo`` no se leyó de las notas (``None``, vacío o el supuesto)."""
    valor = getattr(r, campo)
    if isinstance(valor, dict):
        return valor == {}
    return valor is None or valor.fuente == "supuesto"


_TEMA = {
    "traslape_max_numero": "hasta qué varilla se traslapa",
    "soldar_desde_numero": "desde qué varilla se suelda",
    "gancho_estribo": "ganchos",
    "gancho_grapa": "ganchos",
    "primer_estribo_m": "primer estribo",
    "plantilla_espesor_m": "plantilla",
}
_T, _S, _E = "traslape_max_numero", "soldar_desde_numero", "gancho_estribo"
_P, _PL = "primer_estribo_m", "plantilla_espesor_m"


@pytest.mark.parametrize(
    ("texto", "campo"),
    [
        # 1. la negación va después de la frase, en la misma cláusula
        ("TRASLAPAR VARILLAS DEL #8 AL #12 NO ESTA PERMITIDO", _T),
        ("TRASLAPAR VARILLAS DEL #8 AL #12 ESTA PROHIBIDO", _T),
        ("TRASLAPAR VARILLAS DEL No. 8 AL No. 12 ESTA PROHIBIDO", _T),
        ("LA SOLDADURA EN VARILLAS DEL #8 EN ADELANTE NO ESTA PERMITIDA", _S),
        ("LA SOLDADURA EN VARILLAS DEL #8 EN ADELANTE QUEDA PROHIBIDA", _S),
        ("LA SOLDADURA DE VARILLAS DEL No. 8 EN ADELANTE QUEDA PROHIBIDA", _S),
        ("LOS ESTRIBOS CON GANCHOS A 90° NO SE ACEPTARAN", _E),
        ("ESTRIBOS CON GANCHOS A 90° NO SE PERMITEN, USAR 135°", _E),
        ("LOS TRASLAPES HASTA EL #6 NO SE PERMITEN EN COLUMNAS", _T),
        ("PLANTILLA DE 5 CM NO REQUERIDA", _PL),
        ("EL PRIMER ESTRIBO EN TRABES A 6 CM NO ES OBLIGATORIO", _P),
        # 2. una negación de una cláusula anterior manda sobre la que no tiene verbo propio
        ("NO SE PERMITIRA, EN NINGUN CASO, TRASLAPAR VARILLAS DEL #8 AL #12", _T),
        ("QUEDA PROHIBIDO, SALVO INDICACION, TRASLAPAR VARILLA HASTA EL #6", _T),
        ("NO SE PERMITIRA: TRASLAPAR VARILLAS DEL #8 AL #12", _T),
        ("PROHIBIDO: SE TRASLAPARAN VARILLAS DEL #8 AL #12", _T),
        ("EN NINGUN CASO, SE TRASLAPARAN VARILLAS DEL #8 AL #12", _T),
        ("NO SE PERMITIRA, LAS VARILLAS DEL #8 EN ADELANTE SE SOLDARAN", _S),
        # 6. «evitar» no es permitir, ni un verbo en infinitivo dice una regla
        ("SE EVITARA TRASLAPAR VARILLAS DEL #8 AL #12", _T),
        ("EVITAR TRASLAPAR VARILLA HASTA EL #6", _T),
        ("TRASLAPAR VARILLAS HASTA EL No. 6 Y SOLDAR DEL No. 8 EN ADELANTE", _T),
        ("TRASLAPAR VARILLAS HASTA EL No. 6 Y SOLDAR DEL No. 8 EN ADELANTE", _S),
        # un alcance que la cláusula no dice entera (otra familia, una excepción, otro límite)
        ("SE PERMITE TRASLAPAR VARILLA HASTA EL #6, EXCEPTO EN COLUMNAS", _T),
        ("SE PERMITE TRASLAPAR VARILLA HASTA EL #6, EN COLUMNAS HASTA EL #5", _T),
        ("SE PERMITE TRASLAPAR VARILLA HASTA EL #6 Y EN COLUMNAS HASTA EL #5", _T),
        ("PARA TRASLAPES EN COLUMNAS, SE PERMITE TRASLAPAR VARILLA HASTA EL #5", _T),
        ("SE PERMITE TRASLAPAR, EXCEPTO EN COLUMNAS, VARILLA HASTA EL #6", _T),
        ("LOS TRASLAPES NO SE PERMITEN EN COLUMNAS, SE PERMITE TRASLAPAR VARILLA HASTA EL #6", _T),
        ("SE PERMITE TRASLAPAR HASTA EL 8 EN TRABES, SE PERMITE TRASLAPAR VARILLA HASTA EL #6", _T),
        ("EN COLUMNAS, LOS ESTRIBOS LLEVARAN GANCHOS A 90°", _E),
        ("LOS ESTRIBOS LLEVARAN GANCHOS A 135°, LOS DE COLUMNAS A 90°", _E),
        ("SE PERMITE TRASLAPAR VARILLA HASTA EL #6 Y NO MAYORES", _T),
        ("SE PERMITE TRASLAPAR VARILLA HASTA EL #6, NO MAYORES", _T),
        # 7. una frase que cruza una coma no se lee
        ("LA SOLDADURA SERA CON ELECTRODO E70, LOS TRASLAPES EN VARILLAS DEL #3 EN ADELANTE", _S),
        ("LA SOLDADURA SERA CON ELECTRODO E70, LOS TRASLAPES EN VARILLAS DEL #3 EN ADELANTE", _T),
        # una oración colgada que sigue cambia lo que dice la de antes
        ("SE PERMITE TRASLAPAR VARILLA HASTA EL #6. NO EN COLUMNAS.", _T),
        ("SE PERMITE TRASLAPAR VARILLA HASTA EL #6. EXCEPTO EN COLUMNAS.", _T),
        ("SE PERMITE TRASLAPAR VARILLA HASTA EL #6. EN COLUMNAS SOLO HASTA EL #5.", _T),
        ("ESTRIBOS CON GANCHOS A 90°. NO SE ACEPTARAN.", _E),
        ("LOS ESTRIBOS LLEVARAN GANCHOS A 135° CON TRAMO RECTO DE 10Ø. EN COLUMNAS A 90°.", _E),
        ("PLANTILLA DE 5 CM DE ESPESOR. EN MUROS 10 CM.", _PL),
        ("EN TRABES EL PRIMER ESTRIBO SE COLOCARA A 5 CM. NO SE ACEPTARA.", _P),
        ("LAS VARILLAS DEL #8 EN ADELANTE SE SOLDARAN; EN COLUMNAS DEL #10 EN ADELANTE", _S),
        # la misma regla dicha otra vez de un modo que no se lee: no se usa ninguna
        (
            "SE PERMITE TRASLAPAR VARILLA HASTA EL #6. EN COLUMNAS SOLO SE TRASLAPARA HASTA EL #5.",
            _T,
        ),
        (
            "LAS VARILLAS DEL #8 EN ADELANTE SE SOLDARAN. EN COLUMNAS LA SOLDADURA SERA "
            "DESDE EL #10.",
            _S,
        ),
        (
            "LOS ESTRIBOS LLEVARAN GANCHOS A 135°. EN COLUMNAS LOS ESTRIBOS TENDRAN GANCHOS A 90°.",
            _E,
        ),
        (
            "SE PERMITE TRASLAPAR VARILLA HASTA EL #6. LOS ESTRIBOS SERAN DEL #3. EN COLUMNAS "
            "HASTA EL #5.",
            _T,
        ),
        (
            "EN TRABES EL PRIMER ESTRIBO SE COLOCARA A 5 CM. EL PRIMER ESTRIBO EN COLUMNAS "
            "A 10 CM.",
            _P,
        ),
        ("PLANTILLA DE 5 CM DE ESPESOR. SOBRE LA PLANTILLA SE COLARA UN FIRME DE 10 CM.", _PL),
    ],
)
def test_a_rule_that_is_negated_or_not_said_whole_is_never_read_and_is_reported(
    tmp_path, texto, campo
):
    r = _con_notas(tmp_path, [f"4. {texto}"])
    assert _sin_lectura(r, campo), getattr(r, campo)
    assert any(_TEMA[campo] in a for a in r.avisos), r.avisos


def test_a_plantilla_that_is_negated_is_not_read_in_a_loose_text_either(tmp_path):
    r = leer_reglas(
        _dibujo(tmp_path, tabla=False, mtexts=[("PLANTILLA DE 5 CM NO REQUERIDA", 5.0, 5.0)]),
        frames=[],
    )
    assert r.plantilla_espesor_m is None
    (aviso,) = r.avisos
    assert "el espesor de la plantilla" in aviso


_NOTA_4_DE_MARINA = (
    "4. NO SE PERMITIRA TRASLAPAR NI SOLDAR MAS DEL 50%%% DEL REFUERZO EN UNA MISMA SECCION, "
    "UNICAMENTE SE PERMITIRA TRASLAPAR VARILLA HASTA EL {tope}, DEL {desde} Y DIAMETROS "
    "MAYORES SE SOLDARAN COMO LO INDICA LA FIG-D."
)


@pytest.mark.parametrize(("tope", "desde"), [("#6", "#8"), ("#8", "#10")])
def test_both_real_wordings_of_marinas_note_4_read_lap_and_weld(tmp_path, tope, desde):
    r = _con_notas(tmp_path, [_NOTA_4_DE_MARINA.format(tope=tope, desde=desde)])
    assert r.traslape_max_numero.valor == tope[1:] and r.soldar_desde_numero.valor == desde[1:]
    assert r.avisos == []


def test_the_foundation_note_of_prueba_1_reads_its_plantilla(tmp_path):
    texto = (
        "2. TODA CIMENTACION SE DESPLANTARA SOBRE UNA PLANTILLA DE CONCRETO f'c = 100 kg/cm2 Y "
        "5.0 cm. DE ESPESOR A LAS PROFUNDIDADES INDICADAS."
    )
    r = _con_notas(tmp_path, [texto], titulo="NOTAS :")
    assert r.plantilla_espesor_m.valor == 0.05 and r.plantilla_espesor_m.fuente == "nota"
    assert r.avisos == []


@pytest.mark.parametrize(
    "texto",
    [
        "LOS ESTRIBOS SE COLOCARAN @ 10 CM. EN LAS ESCUADRAS SE USARAN GANCHOS A 90°",
        "ESTRIBOS DEL #3 @ 20 CM. EN DALAS LAS VARILLAS LLEVARAN GANCHOS A 90°",
        "LOS ESTRIBOS SE COLOCARAN @ 10 CM. A LAS VARILLAS DE ESQUINA SE LES HARAN GANCHOS A 90°",
        "LOS ESTRIBOS SE COLOCARAN @ 10 CM. Y LAS ESCUADRAS LLEVARAN GANCHOS A 90°",
    ],
)
def test_the_hook_of_a_sentence_after_a_unit_period_is_not_the_stirrups(tmp_path, texto):
    r = _con_notas(tmp_path, [f"7. {texto}"])
    assert r.gancho_estribo.fuente == "supuesto" and r.gancho_grapa.fuente == "supuesto"


def test_a_sentence_after_a_unit_period_gives_the_first_stirrup_to_its_own_family(tmp_path):
    texto = "EN COLUMNAS LOS ESTRIBOS IRAN @ 15 CM. EN TRABES EL PRIMER ESTRIBO SE COLOCARA A 5 CM"
    r = _con_notas(tmp_path, [f"3. {texto}"])
    assert {f: d.valor for f, d in r.primer_estribo_m.items()} == {
        "trabe": 0.05,
        "contratrabe": 0.05,
    }


def test_a_first_stirrup_keeps_its_family_and_reports_the_value_of_another_one(tmp_path):
    texto = "3. EN TRABES EL PRIMER ESTRIBO SE COLOCARA A 5 CM. EN COLUMNAS A 10 CM."
    r = _con_notas(tmp_path, [texto])
    assert {f: d.valor for f, d in r.primer_estribo_m.items()} == {
        "trabe": 0.05,
        "contratrabe": 0.05,
    }
    (aviso,) = r.avisos
    assert "el primer estribo" in aviso and "«EN COLUMNAS A 10 CM.»" in aviso


def test_a_new_sentence_after_a_unit_period_starts_where_its_own_subject_does():
    assert len(_frases("LOS ESTRIBOS SE COLOCARAN @ 10 CM. EN LAS ESCUADRAS SE USARAN")) == 2
    assert len(_frases("LOS ESTRIBOS SE COLOCARAN @ 10 CM. A LAS VARILLAS DE ESQUINA")) == 2
    assert len(_frases("LOS ESTRIBOS SE COLOCARAN @ 10 CM. Y LAS ESCUADRAS LLEVARAN")) == 2
    assert len(_frases("LOS ESTRIBOS IRAN @ 15 CM. EN TRABES EL PRIMER ESTRIBO")) == 2
    # «… @ 15CM. Y TENDRAN GANCHOS» no trae sujeto propio: sigue la misma oración.
    assert len(_frases("LOS ESTRIBOS DEL NO. 3 SE COLOCARAN @ 15CM. Y TENDRAN GANCHOS")) == 1


@pytest.mark.parametrize(
    "texto",
    [
        "SE PERMITE TRASLAPAR HASTA 2 O 3 VARILLAS POR SECCION",
        "SE PERMITE TRASLAPAR HASTA 2 A LA VEZ",
        "SE PERMITE TRASLAPAR HASTA 2, EN UNA MISMA SECCION",
        "SE PERMITE TRASLAPAR HASTA 3 Y NO MAS VARILLAS EN UNA SECCION",
        "SE PERMITE TRASLAPAR HASTA 3 DE ELLAS",
        "SE PERMITE TRASLAPAR HASTA 4 AL MISMO TIEMPO",
        "SE PERMITE TRASLAPAR HASTA 6",
        "SE PERMITE TRASLAPAR HASTA EL 50 % DEL REFUERZO",
        "SE PERMITE TRASLAPAR HASTA EL 50 POR CIENTO DEL REFUERZO",
        "LOS TRASLAPES SE PERMITEN HASTA 2 VARILLAS POR SECCION",
    ],
)
def test_a_count_is_never_a_bar(tmp_path, texto):
    r = _con_notas(tmp_path, [f"4. {texto}"])
    assert r.traslape_max_numero is None and r.soldar_desde_numero is None


@pytest.mark.parametrize(
    "texto",
    [
        "PLANTILLA DE 10 CM A CADA LADO",
        "PLANTILLA DE 10 CM A CADA LADO DE LA ZAPATA",
        "PLANTILLA DE 10 CM EN CADA LADO",
        "PLANTILLA 10 CM MAYOR QUE LA ZAPATA",
        "PLANTILLA DE 10 CM ALREDEDOR DE LA ZAPATA",
        "PLANTILLA DE 10 CM MAS ANCHA QUE LA ZAPATA",
        "SOBRE LA PLANTILLA SE COLARA UN FIRME CON 10 CM DE ESPESOR",
        "PLANTILLA DE CONCRETO POBRE Y FIRME DE 10 CM DE ESPESOR",
        "PLANTILLA DE CONCRETO POBRE, LOSA DE 10 CM DE ESPESOR",
        "PLANTILLA DE 5 CM Y 10 CM DE ESPESOR",
        "NO SE REQUIERE PLANTILLA DE 5 CM",
    ],
)
def test_a_plantilla_measure_that_is_not_its_thickness_is_reported_never_read(tmp_path, texto):
    r = leer_reglas(_dibujo(tmp_path, tabla=False, mtexts=[(texto, 5.0, 5.0)]), frames=[])
    assert r.plantilla_espesor_m is None, texto
    assert any("el espesor de la plantilla" in a for a in r.avisos), r.avisos
    r = _con_notas(tmp_path, [f"2. {texto}"], titulo="NOTAS :")
    assert r.plantilla_espesor_m is None, texto
    assert any("el espesor de la plantilla" in a for a in r.avisos), r.avisos


def test_an_unquoted_mixed_fraction_is_reported_not_read(tmp_path):
    r = _con_notas(tmp_path, ["4. SE PERMITE TRASLAPAR VARILLAS HASTA 1 1/4"])
    assert r.traslape_max_numero is None
    assert any("«1 1/4» no se sabe si son pulgadas" in a for a in r.avisos), r.avisos


@pytest.mark.parametrize(
    "texto",
    [
        "LOS ESTRIBOS LLEVARAN GANCHOS A 135° Y LOS ESTRIBOS A 90°",
        "LOS ESTRIBOS LLEVARAN GANCHOS A 135° Y LOS ESTRIBOS DE COLUMNA A 90°",
    ],
)
def test_a_second_angle_for_the_same_hook_is_never_dropped_silently(tmp_path, texto):
    r = _con_notas(tmp_path, [f"7. {texto}"])
    assert r.gancho_estribo.fuente == "supuesto"
    assert any("los ganchos de estribos y grapas" in a for a in r.avisos), r.avisos


def test_a_lap_with_a_weld_that_is_denied_reads_the_lap_and_says_nothing_more(tmp_path):
    r = _con_notas(tmp_path, ["4. SE TRASLAPARAN HASTA EL #6 Y NO SE SOLDARA NINGUNA"])
    assert r.traslape_max_numero.valor == "6" and r.soldar_desde_numero is None
    assert r.avisos == []


@pytest.mark.parametrize(
    ("texto", "traslape", "soldar"),
    [
        ("SE TRASLAPARAN VARILLAS HASTA EL No 6", "6", None),
        ("SE PERMITE TRASLAPAR VARILLAS HASTA EL No.6", "6", None),
        ("SE TRASLAPARAN VARILLAS HASTA EL NO. 6, DEL NO. 8 EN ADELANTE SE SOLDARAN", "6", "8"),
        (
            "SOLO SE TRASLAPARA VARILLA DEL No. 3 AL No. 6, DEL No. 8 EN ADELANTE SE SOLDARA",
            "6",
            "8",
        ),
        ("SE TRASLAPARAN VARILLAS HASTA No. 6, LAS DE No. 8 O MAYORES SE SOLDARAN", "6", "8"),
        ("DE LA No. 8 EN ADELANTE SE SOLDARA; HASTA LA No. 6 SE TRASLAPARA", "6", "8"),
        ("EL TRASLAPE SERA SEGUN TABLA, DEL No. 6 EN ADELANTE SE SOLDARA", None, "6"),
        ("SE PERMITE TRASLAPAR VARILLA HASTA EL #6 COMO LO INDICA LA FIG-D", "6", None),
        ("SE PERMITE TRASLAPAR VARILLA HASTA EL #6 (VER TABLA No. 1)", "6", None),
        ("SE PERMITE TRASLAPAR, VER DETALLE 3, VARILLA HASTA EL #6", "6", None),
        ("SE PERMITE TRASLAPAR VARILLA HASTA EL #6. VER DETALLE 3.", "6", None),
        ('SE PERMITE TRASLAPAR VARILLAS HASTA EL No. 6 (3/4")', "6", None),
        ("SALVO INDICACION, SE PERMITE TRASLAPAR VARILLA HASTA EL #6", "6", None),
        ("SIN EMBARGO SE PERMITE TRASLAPAR VARILLA HASTA EL #6", "6", None),
        ("SE PERMITE TRASLAPAR VARILLA HASTA EL #6 Y DEL #8 EN ADELANTE SE SOLDARAN", "6", "8"),
        ("SE PERMITE TRASLAPAR VARILLA HASTA EL #6 Y LAS DEMAS SE SOLDARAN", "6", None),
    ],
)
def test_phrasings_whose_every_clause_is_understood_are_read(tmp_path, texto, traslape, soldar):
    r = _con_notas(tmp_path, [f"4. {texto}"])
    assert (r.traslape_max_numero and r.traslape_max_numero.valor) == traslape
    assert (r.soldar_desde_numero and r.soldar_desde_numero.valor) == soldar


def test_an_inch_equivalence_that_says_another_bar_is_reported(tmp_path):
    r = _con_notas(tmp_path, ['4. SE PERMITE TRASLAPAR VARILLA HASTA EL #6 (3/8")'])
    assert r.traslape_max_numero is None
    assert any("no son la misma varilla" in a for a in r.avisos), r.avisos


def test_hooks_with_their_own_angle_each_and_one_denied(tmp_path):
    texto = "7. LAS GRAPAS LLEVARAN GANCHOS A 180° Y LOS ESTRIBOS A 135° CON TRAMO RECTO DE 10Ø"
    r = _con_notas(tmp_path, [texto])
    assert r.gancho_estribo.valor == {"angulo": 135, "recto_diametros": 10}
    assert r.gancho_grapa.valor == {"angulo": 180, "recto_diametros": 10}
    texto = "7. LOS ESTRIBOS LLEVARAN GANCHOS A 135° Y LAS GRAPAS NO LLEVARAN GANCHOS A 180°"
    r = _con_notas(tmp_path, [texto])  # R40: la parte negada es de la nota: no se usa nada
    assert r.gancho_estribo.fuente == "supuesto" and r.gancho_grapa.fuente == "supuesto"
    assert any("180°" in a for a in r.avisos)
    r = _con_notas(tmp_path, ["7. LOS ESTRIBOS NO LLEVARAN GANCHOS A 90° Y LAS GRAPAS A 180°"])
    assert r.gancho_estribo.fuente == "supuesto" and r.gancho_grapa.fuente == "supuesto"
    assert any("los ganchos de estribos y grapas" in a for a in r.avisos)


@pytest.mark.parametrize(
    "texto",
    [
        "EL RECUBRIMIENTO NO SERA DE 5 CM EN TRABES",
        "EL RECUBRIMIENTO SERA 5.0 CM EN COLUMNAS, NO EN TRABES",
        "EL RECUBRIMIENTO SERA 5.0 CM EN COLUMNAS EXCEPTO TRABES",
        "EL RECUBRIMIENTO SERA 5.0 CM EN COLUMNAS NI 4 CM EN TRABES",
    ],
)
def test_a_cover_that_a_note_denies_or_excepts_is_not_read(tmp_path, texto):
    r = _con_notas(tmp_path, [f"4. {texto}"], titulo="NOTAS :")
    assert r.recubrimiento_m["trabe"].fuente == "supuesto"
    assert r.avisos


def test_a_plantilla_in_meters_after_its_material_is_not_read_without_its_thickness(tmp_path):
    """«PLANTILLA DE CONCRETO POBRE DE 0.10 M» puede ser lo que sobresale, no el espesor: en metros
    sólo se lee pegada a la palabra o con «ESPESOR»."""
    texto = "PLANTILLA DE CONCRETO POBRE DE 0.10 M"
    r = leer_reglas(_dibujo(tmp_path, tabla=False, mtexts=[(texto, 5.0, 5.0)]), frames=[])
    assert r.plantilla_espesor_m is None
    (aviso,) = r.avisos
    assert "el espesor de la plantilla" in aviso


def test_a_negation_well_before_a_cover_still_cancels_it(tmp_path):
    r = _con_notas(tmp_path, ["4. EL RECUBRIMIENTO NUNCA SERA DE 5 CM EN TRABES"], titulo="NOTAS :")
    assert r.recubrimiento_m["trabe"].fuente == "supuesto"
    (aviso,) = r.avisos
    assert "el recubrimiento" in aviso and "no se pudo leer" in aviso


@pytest.mark.parametrize(
    "texto",
    [
        "SE PERMITE TRASLAPAR VARILLA HASTA EL #6 VER DETALLE NUNCA",
        "SE PERMITE TRASLAPAR VARILLA HASTA EL #6 (NO MAYOR)",
    ],
)
def test_a_negation_inside_what_follows_a_bar_is_never_read(tmp_path, texto):
    r = _con_notas(tmp_path, [f"4. {texto}"])
    assert r.traslape_max_numero is None and r.avisos


@pytest.mark.parametrize(
    "texto",
    ["LAS VARILLAS DEL #8 SE SOLDARAN", "SOLDAR VARILLAS SEGUN AWS D1.4 DEL No. 8"],
)
def test_a_weld_that_names_a_bar_without_a_limit_word_is_reported(tmp_path, texto):
    r = _con_notas(tmp_path, [f"4. {texto}"])
    assert r.soldar_desde_numero is None
    (aviso,) = r.avisos
    assert "desde qué varilla se suelda" in aviso


@pytest.mark.parametrize(
    ("palabras", "tipo", "escrito"),
    [
        ("HASTA EL #6", "num", "6"),
        ("HASTA NO. 6", "num", "6"),  # «No. 6» en mayúsculas sin acentos
        ("HASTA EL 6", "num", "6"),
        ("HASTA LA VARILLA 6", "num", "6"),
        ("HASTA 6", "pelado", "6"),
        ('HASTA 3/4"', "pulg", '3/4"'),
        ("HASTA 5/8 PULG", "pulg", "5/8 PULG"),
        ("HASTA 3/4", "fraccion", "3/4"),
        ("HASTA 1 1/4", "fraccion", "1 1/4"),
    ],
)
def test_a_bar_in_a_phrase_is_what_its_words_say(palabras, tipo, escrito):
    import re

    from klave_engine.estructura.frases import _HASTA, varilla_de

    m = re.fullmatch(_HASTA, palabras)
    v = varilla_de(m, "b", con_cola=False)
    assert (v.tipo, v.escrito) == (tipo, escrito)


def test_a_known_phrase_is_read_only_when_it_covers_its_whole_clause():
    from klave_engine.estructura.frases import leer_frases

    def reglas(texto):
        lectura = leer_frases(texto, {"traslape", "soldar"})
        return [(f.regla, lectura.texto[f.inicio : f.fin]) for f in lectura.validas()]

    assert reglas("SE PERMITE TRASLAPAR VARILLA HASTA EL #6") == [
        ("traslape", "SE PERMITE TRASLAPAR VARILLA HASTA EL #6")
    ]
    assert reglas("SE PERMITE TRASLAPAR VARILLA HASTA EL #6 EN TRABES") == []
    assert reglas("NO SE PERMITE TRASLAPAR VARILLA HASTA EL #6") == []
    assert reglas("SE PERMITE TRASLAPAR VARILLA HASTA EL #6, DEL #8 EN ADELANTE SE SOLDARAN") == [
        ("traslape", "SE PERMITE TRASLAPAR VARILLA HASTA EL #6"),
        ("soldar", "DEL #8 EN ADELANTE SE SOLDARAN"),
    ]


# --- el generador adversario: frases × negaciones × conteos × contexto -------------------------

_FORMAS_DEL_6 = ("#6", "No. 6", "NUMERO 6", '3/4"')
_FORMAS_DEL_8 = ("#8", "No. 8", "NUM. 8", '1"')
_BASES = (
    # (regla, texto con {B}, formas de la varilla, lo que se lee)
    (_T, "SE PERMITE TRASLAPAR VARILLA HASTA EL {B}", _FORMAS_DEL_6, "6"),
    (_T, "UNICAMENTE SE PERMITIRA TRASLAPAR VARILLA HASTA EL {B}", _FORMAS_DEL_6, "6"),
    (_T, "SE TRASLAPARAN LAS VARILLAS HASTA EL {B}", _FORMAS_DEL_6, "6"),
    (_T, "SE PERMITE TRASLAPAR VARILLAS DEL #3 AL {B}", _FORMAS_DEL_6, "6"),
    (_S, "DEL {B} Y DIAMETROS MAYORES SE SOLDARAN", _FORMAS_DEL_8, "8"),
    (_S, "LAS VARILLAS DEL {B} EN ADELANTE SE SOLDARAN", _FORMAS_DEL_8, "8"),
    (_S, "A PARTIR DEL {B} SE SOLDARAN LAS VARILLAS", _FORMAS_DEL_8, "8"),
    (_S, "SE SOLDARAN LAS VARILLAS DEL {B} EN ADELANTE", _FORMAS_DEL_8, "8"),
)
_CONTEXTOS = (
    "{f} COMO LO INDICA LA FIG-D",
    "{f}, VER DETALLE 3",
    "{f} (VER TABLA No. 1)",
    "SALVO INDICACION, {f}",
)
_NEGACIONES = (
    "NO {f}",
    "NUNCA {f}",
    "{f} NO ESTA PERMITIDO",
    "{f}, NO ESTA PERMITIDO",
    "{f} QUEDA PROHIBIDO",
    "NO SE PERMITIRA, {f}",
    "PROHIBIDO: {f}",
    "QUEDA PROHIBIDO, SALVO INDICACION, {f}",
    "EN NINGUN CASO, {f}",
    "{f}, EXCEPTO EN COLUMNAS",
    "EN COLUMNAS, {f}",
    "{f}, NO EN COLUMNAS",
    "{f}. NO SE ACEPTARA.",
    "{f}. EXCEPTO EN COLUMNAS.",
)
_CONTEOS = (
    "2 VARILLAS POR SECCION",
    "2 O 3 VARILLAS POR SECCION",
    "3 BARRAS",
    "2 A LA VEZ",
    "4 AL MISMO TIEMPO",
    "3 DE LAS 6 VARILLAS",
    "50 % DEL REFUERZO",
    "40 VECES EL DIAMETRO",
    "10Ø",
    "6",
)
_OTRAS_REGLAS = (
    (_E, "LOS ESTRIBOS LLEVARAN GANCHOS A 90° CON TRAMO RECTO DE 6Ø"),
    (_P, "EN TRABES EL PRIMER ESTRIBO SE COLOCARA A 5 CM"),
    (_PL, "SE COLOCARA PLANTILLA DE 8 CM DE ESPESOR"),
)


def _variantes():
    for regla, base, formas, valor in _BASES:
        for forma in formas:
            frase = base.format(B=forma)
            yield pytest.param(frase, regla, valor, id=frase)
            for contexto in _CONTEXTOS:
                texto = contexto.format(f=frase)
                yield pytest.param(texto, regla, valor, id=texto)
        frase = base.format(B=formas[0])
        for negacion in _NEGACIONES:
            texto = negacion.format(f=frase)
            yield pytest.param(texto, regla, None, id=texto)
    for prefijo in (
        "SE PERMITE TRASLAPAR HASTA",
        "SE TRASLAPARAN HASTA",
        "LOS TRASLAPES SE HARAN HASTA",
    ):
        for conteo in _CONTEOS:
            texto = f"{prefijo} {conteo}"
            yield pytest.param(texto, _T, None, id=texto)
    for regla, frase in _OTRAS_REGLAS:
        for negacion in _NEGACIONES:
            texto = negacion.format(f=frase)
            yield pytest.param(texto, regla, None, id=texto)


@pytest.mark.parametrize(("texto", "campo", "valor"), list(_variantes()))
def test_adversarial_variants_read_right_or_not_at_all(tmp_path, texto, campo, valor):
    r = _con_notas(tmp_path, [f"4. {texto}"])
    if valor is None:
        assert _sin_lectura(r, campo), getattr(r, campo)
    else:
        assert getattr(r, campo).valor == valor
        assert r.avisos == [], r.avisos


# --- ronda 5 (R40): la nota entera — sus lecturas valen sólo si nada de ella las niega, las acota
# o se quedó sin leer -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "campo"),
    [
        # 1. lo que manda sobre la frase está antes de un «;» o de un «.»
        ("PROHIBIDO; SE TRASLAPARAN VARILLAS HASTA EL #6", _T),
        ("PROHIBIDO. SE TRASLAPARAN VARILLAS HASTA EL #6", _T),
        ("NO SE PERMITIRA; SE TRASLAPARAN VARILLAS HASTA EL #6", _T),
        ("QUEDA PROHIBIDO; SALVO INDICACION, SE TRASLAPARAN VARILLAS HASTA EL #6", _T),
        ("EN NINGUN CASO; SE TRASLAPARAN VARILLAS HASTA EL #6", _T),
        ("EN COLUMNAS; DEL #8 EN ADELANTE SE SOLDARAN", _S),
        ("PARA COLUMNAS. DEL #8 EN ADELANTE SE SOLDARAN", _S),
        (
            "EN COLUMNAS: LOS ESTRIBOS SERAN DEL #3; SE PERMITE TRASLAPAR VARILLA HASTA EL #6; LAS "
            "VARILLAS DEL #8 EN ADELANTE SE SOLDARAN.",
            _T,
        ),
        (
            "EN COLUMNAS: LOS ESTRIBOS SERAN DEL #3; SE PERMITE TRASLAPAR VARILLA HASTA EL #6; LAS "
            "VARILLAS DEL #8 EN ADELANTE SE SOLDARAN.",
            _S,
        ),
        ("NO SE PERMITIRA: SOLDAR EN CAMPO; SE TRASLAPARAN VARILLAS HASTA EL #6.", _T),
        ("NO SE PERMITE SOLDAR; SE TRASLAPARA HASTA EL #6", _T),
        ("NO SE PERMITIRA TRASLAPAR VARILLA MAYOR AL #6, SE SOLDARAN LAS DEL #8 EN ADELANTE", _S),
        # 2. un diámetro no es un número de varilla (puede ser en milímetros)
        ("SE TRASLAPARAN VARILLAS HASTA DIAMETRO 12", _T),
        ("SE TRASLAPARAN VARILLAS HASTA DIAMETRO 6", _T),
        ("SE TRASLAPARAN VARILLAS HASTA DIAMETRO 12 MM", _T),
        ("SE TRASLAPARAN VARILLAS HASTA 12 MM", _T),
        # 3. una excepción para un elemento, dicha con la otra regla
        ("SE PERMITE TRASLAPAR VARILLA HASTA EL #6, EN COLUMNAS SE SOLDARAN", _T),
        ("SE PERMITE TRASLAPAR VARILLA HASTA EL #6 Y EN COLUMNAS SE SOLDARAN", _T),
        (
            "SE PERMITE TRASLAPAR VARILLA HASTA EL #6. EN COLUMNAS SE SOLDARAN TODAS LAS VARILLAS.",
            _T,
        ),
        ("DEL #8 EN ADELANTE SE SOLDARAN, EN COLUMNAS SE TRASLAPARAN TODAS", _S),
        ("SE PERMITE TRASLAPAR VARILLA HASTA EL #6, NO ASI EN COLUMNAS DONDE SE SOLDARAN", _T),
        ("SE PERMITE TRASLAPAR VARILLA HASTA EL #6. NO SE PERMITEN TRASLAPES EN COLUMNAS.", _T),
        ("SE PERMITE TRASLAPAR VARILLA HASTA EL #6. EN COLUMNAS NO SE PERMITEN TRASLAPES.", _T),
        ("DEL #8 EN ADELANTE SE SOLDARAN. EN COLUMNAS NO SE PERMITE SOLDAR.", _S),
        # 4. lo que amplía o recorta a qué varillas va la regla
        ("SE TRASLAPARAN LAS VARILLAS HASTA EL #4 Y LAS DE MAYOR DIAMETRO TAMBIEN", _T),
        ("SE PERMITE TRASLAPAR VARILLA HASTA EL #6, Y MAYORES TAMBIEN", _T),
        ("LAS VARILLAS DEL #8 EN ADELANTE SE SOLDARAN, ASI COMO LAS MENORES", _S),
        ("LAS VARILLAS DEL #8 EN ADELANTE SE SOLDARAN Y LAS DEMAS TAMBIEN", _S),
        (
            "EN TRABES EL PRIMER ESTRIBO SE COLOCARA A 5 CM. EN CONTRATRABES EL PRIMER ESTRIBO SE "
            "COLOCARA A MEDIA SEPARACION.",
            _P,
        ),
        # una nota anulada
        ("SE PERMITE TRASLAPAR VARILLA HASTA EL #6 (NOTA CANCELADA)", _T),
        ("NOTA ANULADA. SE PERMITE TRASLAPAR VARILLA HASTA EL #6", _T),
        ("N/A: SE PERMITE TRASLAPAR VARILLA HASTA EL #6", _T),
        # 6. un rango cuyo extremo de abajo no es una varilla
        ("SE TRASLAPARAN VARILLAS DEL 1 AL 6", _T),
    ],
)
def test_a_note_whose_rule_is_scoped_negated_or_not_read_whole_is_one_aviso(tmp_path, texto, campo):
    r = _con_notas(tmp_path, [f"4. {texto}"])
    assert _sin_lectura(r, campo), getattr(r, campo)
    assert r.avisos, texto


def test_the_aviso_of_a_note_that_is_not_used_quotes_it_and_says_why(tmp_path):
    texto = "SE PERMITE TRASLAPAR VARILLA HASTA EL #6. NO SE PERMITEN TRASLAPES EN COLUMNAS."
    r = _con_notas(tmp_path, [f"4. {texto}"])
    (aviso,) = r.avisos
    assert aviso.startswith("La nota 4 de REFUERZO dice hasta qué varilla se traslapa")
    assert "«NO SE PERMITEN TRASLAPES EN COLUMNAS»" in aviso and "no se usa nada" in aviso
    assert texto in aviso


@pytest.mark.parametrize(
    ("encabezado", "renglon", "campo"),
    [
        ("COLUMNAS :", "1. SE PERMITE TRASLAPAR VARILLA HASTA EL #6", _T),
        ("NOTAS PARA LOSAS :", "1. LAS VARILLAS DEL #8 EN ADELANTE SE SOLDARAN", _S),
        ("COLUMNAS :", "1. EN TRABES EL PRIMER ESTRIBO SE COLOCARA A 5 CM", _P),
    ],
)
def test_a_heading_that_names_an_element_scopes_its_notes(tmp_path, encabezado, renglon, campo):
    r = _con_notas(tmp_path, [renglon], titulo=encabezado)
    assert _sin_lectura(r, campo), getattr(r, campo)
    assert r.avisos


def test_a_per_family_rule_under_a_heading_is_read_for_that_family(tmp_path):
    r = _con_notas(
        tmp_path, ["1. EL PRIMER ESTRIBO SE COLOCARA A 5 CM DEL PAÑO"], titulo="COLUMNAS :"
    )
    assert {f: d.valor for f, d in r.primer_estribo_m.items()} == {"columna": 0.05}
    assert r.avisos == []


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("EL RECUBRIMIENTO SERA 5 CM EN TRABES DE CIMENTACION", {"contratrabe": 0.05}),
        ("EL RECUBRIMIENTO SERA 5 CM EN LOSA DE CIMENTACION", {"losa_cimentacion": 0.05}),
        (
            "EL RECUBRIMIENTO SERA 4 CM EN TRABES Y 0.05 M EN COLUMNAS",
            {"trabe": 0.04, "columna": 0.05},
        ),
        ("EL RECUBRIMIENTO SERA DE 0.05 M EN TRABES", {"trabe": 0.05}),
    ],
)
def test_covers_of_foundation_beams_and_slabs_and_in_meters_are_read(tmp_path, texto, esperado):
    r = _con_notas(tmp_path, [f"4. {texto}"], titulo="NOTAS :")
    leidos = {k: d.valor for k, d in r.recubrimiento_m.items() if d.fuente == "nota"}
    assert leidos == esperado and r.avisos == []


@pytest.mark.parametrize(
    ("texto", "nunca"),
    [
        ("EL RECUBRIMIENTO SERA 5 CM EN COLUMNAS DE CIMENTACION", "columna"),
        ("EL RECUBRIMIENTO SERA 4 CM EN TRABES, COLUMNAS 3 CM", "columna"),
        ("EL RECUBRIMIENTO SERA 4 CM EN TRABES; COLUMNAS: 5 CM", "columna"),
        ("EL RECUBRIMIENTO SERA 4 CM EN TRABES. EN LOSAS 2 CM.", "losa"),
        ("EL RECUBRIMIENTO SERA 4 CM EN TRABES Y DE CINCO CENTIMETROS EN COLUMNAS", "columna"),
        ("EL RECUBRIMIENTO SERA 4 CM EN TRABES Y LA MITAD EN LOSAS", "losa"),
        ("EL RECUBRIMIENTO SERA 4 CM EN TRABES Y DEL DOBLE EN COLUMNAS", "columna"),
        ("EL RECUBRIMIENTO SERA 4 CM EN TRABES MAS 1 CM EN COLUMNAS", "columna"),
    ],
)
def test_a_cover_is_never_given_to_an_element_it_was_not_said_for(tmp_path, texto, nunca):
    r = _con_notas(tmp_path, [f"4. {texto}"], titulo="NOTAS :")
    assert r.recubrimiento_m[nunca].fuente == "supuesto"
    assert r.avisos


def test_an_anchorage_into_an_element_is_not_that_elements_anchorage(tmp_path):
    r = leer_reglas(
        _dibujo(tmp_path, tabla=False, mtexts=[("60 CM DE ANCLAJE EN DALA", 5.0, 5.0)]), frames=[]
    )
    assert r.anclajes_declarados_m == {} and r.avisos
    r = leer_reglas(
        _dibujo(tmp_path, tabla=False, mtexts=[("ANCLAJE DE DALA 60 CM", 5.0, 5.0)]), frames=[]
    )
    assert r.anclajes_declarados_m["dala"].valor == 0.6


@pytest.mark.parametrize(
    "texto",
    ["LAS VARILLAS DE 8 EN ADELANTE SE SOLDARAN", "LAS VARILLAS DE 8 Y MAYORES SE SOLDARAN"],
)
def test_bars_of_a_number_named_as_bars_are_read(tmp_path, texto):
    r = _con_notas(tmp_path, [f"4. {texto}"])
    assert r.soldar_desde_numero.valor == "8" and r.avisos == []


@pytest.mark.parametrize("texto", ["PLANTILLA DE 5", "PLANTILLA DE 0.05"])
def test_a_plantilla_without_a_unit_is_reported(tmp_path, texto):
    r = leer_reglas(_dibujo(tmp_path, tabla=False, mtexts=[(texto, 5.0, 5.0)]), frames=[])
    assert r.plantilla_espesor_m is None and r.avisos
    r = _con_notas(tmp_path, [f"2. {texto}"], titulo="NOTAS :")
    assert r.plantilla_espesor_m is None and r.avisos


def test_a_figure_key_after_its_abbreviation_does_not_end_the_sentence(tmp_path):
    assert len(_frases("LOS ESTRIBOS SEGUN FIG. B LLEVARAN GANCHOS A 90°")) == 1
    r = _con_notas(
        tmp_path, ["7. LOS ESTRIBOS SEGUN FIG. B LLEVARAN GANCHOS A 90° Y TRAMO RECTO DE 6Ø"]
    )
    assert r.gancho_estribo.valor == {"angulo": 90, "recto_diametros": 6}


_ENVOLTURAS = (
    "PROHIBIDO; {f}",
    "PROHIBIDO. {f}",
    "NO SE PERMITIRA; {f}",
    "QUEDA PROHIBIDO; SALVO INDICACION, {f}",
    "EN NINGUN CASO; {f}",
    "EN COLUMNAS; {f}",
    "PARA COLUMNAS. {f}",
    "EN COLUMNAS: LOS ESTRIBOS SERAN DEL #3; {f}",
    "NO SE PERMITIRA: SOLDAR EN CAMPO; {f}",
    "{f}; NO EN COLUMNAS",
)
_NUEVE_BASES = (
    *((regla, base.format(B=formas[0])) for regla, base, formas, _ in _BASES),
    (_E, "LOS ESTRIBOS LLEVARAN GANCHOS A 90° CON TRAMO RECTO DE 6Ø"),
)


@pytest.mark.parametrize(
    ("texto", "campo"),
    [
        pytest.param(envoltura.format(f=frase), regla, id=envoltura.format(f=frase))
        for regla, frase in _NUEVE_BASES
        for envoltura in _ENVOLTURAS
    ],
)
def test_a_governing_clause_before_a_semicolon_or_a_period_is_never_read_globally(
    tmp_path, texto, campo
):
    r = _con_notas(tmp_path, [f"4. {texto}"])
    assert _sin_lectura(r, campo), getattr(r, campo)


@pytest.mark.parametrize(
    ("texto", "campo"),
    [
        # una regla por familia: otra oración que nombra una familia que se leyó la cambia
        ("EN TRABES EL PRIMER ESTRIBO SE COLOCARA A 5 CM. EN CONTRATRABES SEGUN EL DETALLE.", _P),
        # … y en su misma oración, el valor de otra familia que no se lee
        ("EN TRABES, EL PRIMER ESTRIBO SE COLOCARA A 5 CM, EN COLUMNAS A 10 CM", _P),
        # lo que sólo acompaña a la otra regla no vale sin ella
        ("SE PERMITE TRASLAPAR VARILLA HASTA EL #6. NO SE TRASLAPARAN.", _T),
        ("LAS VARILLAS DEL #8 EN ADELANTE SE SOLDARAN. NO SE SOLDARA NINGUNA.", _S),
    ],
)
def test_a_per_family_rule_or_a_companion_that_the_note_contradicts_is_not_used(
    tmp_path, texto, campo
):
    r = _con_notas(tmp_path, [f"3. {texto}"])
    assert _sin_lectura(r, campo), getattr(r, campo)
    assert r.avisos


def test_a_cover_that_another_sentence_says_more_about_is_not_used(tmp_path):
    texto = (
        "4. EL RECUBRIMIENTO SERA 4 CM EN TRABES. EN TRABES DE BORDE CONSULTAR AL ESTRUCTURISTA."
    )
    r = _con_notas(tmp_path, [texto], titulo="NOTAS :")
    assert r.recubrimiento_m["trabe"].fuente == "supuesto" and r.avisos


# --- Task 5b (R41): encabezados con un elemento calificado, «DE CIMENTACION» coordinado, más
# palabras de alcance, más maneras de anular una nota, «NO.» al final, más diámetros -------------

_L = "SE PERMITE TRASLAPAR VARILLA HASTA EL #6"


@pytest.mark.parametrize(
    ("encabezado", "renglon", "esperado"),
    [
        # A. «TRABES DE CIMENTACION» son las contratrabes; un elemento calificado no se sabe leer
        (
            "NOTAS PARA TRABES DE CIMENTACION :",
            "EL PRIMER ESTRIBO SE COLOCARA A 5 CM",
            {"contratrabe": 0.05},
        ),
        ("TRABES Y LOSAS DE CIMENTACION :", "EL PRIMER ESTRIBO SE COLOCARA A 5 CM", {}),
        ("NOTAS PARA TRABES PRECOLADAS :", "EL PRIMER ESTRIBO SE COLOCARA A 5 CM", {}),
        ("VIGAS :", "EL PRIMER ESTRIBO SE COLOCARA A 5 CM", {"trabe": 0.05, "contratrabe": 0.05}),
    ],
)
def test_the_first_stirrup_takes_only_the_families_its_heading_really_names(
    tmp_path, encabezado, renglon, esperado
):
    r = _con_notas(tmp_path, [f"1. {renglon}"], titulo=encabezado)
    assert {f: d.valor for f, d in r.primer_estribo_m.items()} == esperado
    assert bool(r.avisos) == (esperado == {})


@pytest.mark.parametrize(
    "encabezado",
    [
        "NOTAS PARA TRABES DE CIMENTACION :",
        "NOTAS PARA TRABES PRECOLADAS :",
        "TRABES Y LOSAS DE CIMENTACION :",
    ],
)
def test_a_cover_outside_what_its_heading_names_is_not_read(tmp_path, encabezado):
    r = _con_notas(tmp_path, ["1. EL RECUBRIMIENTO LIBRE SERA: 4 CM EN TRABES"], titulo=encabezado)
    assert r.recubrimiento_m["trabe"].fuente == "supuesto" and r.avisos


@pytest.mark.parametrize(
    "encabezado",
    ["VIGAS :", "NOTAS PARA VIGAS :", "SUPERESTRUCTURA :", "NOTAS PARA NERVADURAS :", "AZOTEA :"],
)
def test_a_heading_that_names_a_part_of_the_structure_scopes_a_project_rule(tmp_path, encabezado):
    r = _con_notas(tmp_path, [f"1. {_L}"], titulo=encabezado)
    assert r.traslape_max_numero is None and r.avisos


@pytest.mark.parametrize("encabezado", ["NOTAS DE CIMENTACION :", "NOTAS DE CIMENTACIÓN :"])
def test_the_foundation_notes_heading_is_generic(tmp_path, encabezado):
    r = _con_notas(tmp_path, [f"1. {_L}"], titulo=encabezado)
    assert r.traslape_max_numero.valor == "6" and r.avisos == []


@pytest.mark.parametrize(
    "lista",
    [
        "TRABES Y LOSAS DE CIMENTACION",
        "LOSAS Y TRABES DE CIMENTACION",
        "TRABES Y ZAPATAS DE CIMENTACION",
        "COLUMNAS Y DADOS DE CIMENTACION",
        "TRABES, LOSAS Y ZAPATAS DE CIMENTACION",
    ],
)
def test_a_coordinated_de_cimentacion_is_ambiguous_and_reported(tmp_path, lista):
    r = _con_notas(tmp_path, [f"4. EL RECUBRIMIENTO SERA 5 CM EN {lista}"], titulo="NOTAS :")
    assert all(d.fuente == "supuesto" for d in r.recubrimiento_m.values())
    assert r.avisos


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("EL RECUBRIMIENTO SERA 4 CM EN VIGAS", {"trabe": 0.04}),
        ("RECUBRIMIENTOS: 4 CM EN TRABES", {"trabe": 0.04}),
        ("RECUBRIMIENTOS LIBRES: 4 CM EN TRABES", {"trabe": 0.04}),
        ("LOS RECUBRIMIENTOS SERAN: 4 CM EN TRABES", {"trabe": 0.04}),
    ],
)
def test_plural_cover_lead_ins_and_beams_called_vigas_are_read(tmp_path, texto, esperado):
    r = _con_notas(tmp_path, [f"4. {texto}"], titulo="NOTAS :")
    assert {k: d.valor for k, d in r.recubrimiento_m.items() if d.fuente == "nota"} == esperado
    assert r.avisos == []


_ALCANCES_Y_ANULACIONES = (
    # D. más palabras que acotan
    "{f}, EN VIGAS.",
    "{f}. EN VIGAS.",
    "{f}, EN NERVADURAS.",
    "{f}, EXCLUSIVAMENTE EN NERVADURAS.",
    "{f}, EN LOS MARCOS.",
    "{f}, EN PILAS.",
    "{f}, EN ENTREPISOS.",
    "{f}, EN AZOTEA.",
    "{f}, EN ELEMENTOS SECUNDARIOS.",
    "{f}. EN LA SUPERESTRUCTURA.",
    "{f}, Y LAS SUPERIORES IGUAL",
    # E. más maneras de anular una nota
    "{f}. SE CANCELA.",
    "SE CANCELA ESTA NOTA. {f}",
    "{f}. SE SUPRIME.",
    "{f}. DEROGADA.",
    "{f}. OBSOLETA.",
    "{f}. SUSTITUIDA POR LA NOTA 9.",
    "{f}. REEMPLAZADA POR NOTA 9.",
    "{f}. INVÁLIDA.",
    "{f}. OMITIR.",
    "{f} (OMITIDA)",
    "{f}. NA.",
    "{f}. N.A.",
    # F. «NO.» al final es una negación
    "{f}: NO.",
    "{f}, EN PILAS NO.",
    "{f}; EN MARCOS DUCTILES NO.",
)


@pytest.mark.parametrize(
    ("texto", "campo"),
    [
        pytest.param(envoltura.format(f=frase), regla, id=envoltura.format(f=frase))
        for regla, frase in _NUEVE_BASES
        for envoltura in _ALCANCES_Y_ANULACIONES
    ],
)
def test_a_scope_word_a_cancellation_or_a_final_no_never_lets_a_global_reading_through(
    tmp_path, texto, campo
):
    r = _con_notas(tmp_path, [f"4. {texto}"])
    assert _sin_lectura(r, campo), getattr(r, campo)
    assert r.avisos


@pytest.mark.parametrize(
    ("encabezado", "regla", "frase"),
    [
        pytest.param(encabezado, regla, frase, id=f"{encabezado} {frase}")
        for regla, frase in _NUEVE_BASES
        for encabezado in (
            "VIGAS :",
            "NOTAS PARA VIGAS :",
            "SUPERESTRUCTURA :",
            "NOTAS PARA TRABES PRECOLADAS :",
            "TRABES Y LOSAS DE CIMENTACION :",
        )
    ],
)
def test_a_scoping_heading_never_lets_a_global_reading_through(tmp_path, encabezado, regla, frase):
    r = _con_notas(tmp_path, [f"1. {frase}"], titulo=encabezado)
    assert _sin_lectura(r, regla), getattr(r, regla)


@pytest.mark.parametrize(
    "texto",
    [
        "SE TRASLAPARAN VARILLAS HASTA DIAM. 12",
        "SE TRASLAPARAN VARILLAS HASTA Ø 12",
        "SE TRASLAPARAN VARILLAS HASTA EL Ø 6",
        "SE TRASLAPARAN VARILLAS HASTA LA DE 12 MM",
        "SE TRASLAPARAN VARILLAS HASTA EL CALIBRE 6",
        "DEL DIAMETRO 25 EN ADELANTE SE SOLDARAN",
    ],
)
def test_a_diameter_or_a_gauge_instead_of_a_bar_is_reported(tmp_path, texto):
    r = _con_notas(tmp_path, [f"4. {texto}"])
    assert r.traslape_max_numero is None and r.soldar_desde_numero is None
    (aviso,) = r.avisos
    assert "varilla" in aviso and "no se pudo leer" in aviso


def test_a_bar_number_after_no_is_still_a_bar():
    assert not niega("HASTA EL NO. 6", 0, 14) and not niega("HASTA EL NO.6", 0, 13)
    assert niega("EN PILAS NO.", 0, 12) and niega("TRASLAPAR: NO", 0, 13)


@pytest.mark.parametrize(
    ("texto", "campo", "valor"),
    [
        ("EL RECUBRIMIENTO SERA DE 4 CM EN TRABES, EN LOSAS LA MITAD", "recubrimiento", 0.04),
        (
            "EL RECUBRIMIENTO SERA DE 4 CM EN TRABES. EN COLUMNAS SERA DE CINCO CENTIMETROS.",
            "recubrimiento",
            0.04,
        ),
        (
            "EN TRABES EL PRIMER ESTRIBO SE COLOCARA A 5 CM. EN COLUMNAS A MEDIA SEPARACION.",
            "primer",
            0.05,
        ),
    ],
)
def test_what_a_note_says_of_another_family_without_a_number_is_reported(
    tmp_path, texto, campo, valor
):
    r = _con_notas(tmp_path, [f"4. {texto}"], titulo="NOTAS :")
    if campo == "recubrimiento":
        assert r.recubrimiento_m["trabe"].valor == valor
        assert r.recubrimiento_m["losa"].fuente == r.recubrimiento_m["columna"].fuente == "supuesto"
    else:
        assert r.primer_estribo_m["trabe"].valor == valor and "columna" not in r.primer_estribo_m
    (aviso,) = r.avisos
    assert "además algo que no se pudo leer" in aviso


def test_the_same_for_another_family_extends_the_rule_and_the_note_is_reported(tmp_path):
    r = _con_notas(
        tmp_path, ["4. EN TRABES EL PRIMER ESTRIBO SE COLOCARA A 5 CM, LO MISMO EN COLUMNAS"]
    )
    assert r.primer_estribo_m == {} and r.avisos


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("EN TRABES DE CIMENTACION EL PRIMER ESTRIBO SE COLOCARA A 5 CM", {"contratrabe": 0.05}),
        ("EN VIGAS EL PRIMER ESTRIBO SE COLOCARA A 5 CM", {"trabe": 0.05, "contratrabe": 0.05}),
    ],
)
def test_the_first_stirrup_of_foundation_beams_is_the_contratrabes(tmp_path, texto, esperado):
    r = _con_notas(tmp_path, [f"3. {texto}"])
    assert {f: d.valor for f, d in r.primer_estribo_m.items()} == esperado and r.avisos == []


# --- Task 5b, ronda de arreglos 1 (R42, R43): «DE CIMENTACION» coordinado en el primer estribo,
# una parte de la estructura o un lugar que no se conoce acota, los encabezados de cimentación,
# más anulaciones, la lista con el último calificado, lo que la nota contradice, el N.A.F. y más
# diámetros ------------------------------------------------------------------------------------

_R = "recubrimiento_m"


def _nada_de_la_nota(r, campo):
    """``True`` si ``campo`` no trae nada de las notas (los recubrimientos: todos supuestos)."""
    if campo == _R:
        return all(d.fuente == "supuesto" for d in r.recubrimiento_m.values())
    return _sin_lectura(r, campo)


@pytest.mark.parametrize(
    "texto",
    [
        "EN COLUMNAS Y TRABES DE CIMENTACION EL PRIMER ESTRIBO SE COLOCARA A 5 CM",
        "EL PRIMER ESTRIBO EN COLUMNAS Y TRABES DE CIMENTACION SE COLOCARA A 5 CM",
        "EL PRIMER ESTRIBO DE LAS COLUMNAS Y VIGAS DE CIMENTACION SE COLOCARA A 5 CM",
        "EN TRABES Y VIGAS DE CIMENTACION EL PRIMER ESTRIBO SE COLOCARA A 5 CM",
        "EN DALAS Y TRABES DE CIMENTACION EL PRIMER ESTRIBO SE COLOCARA A 5 CM",
        "EN CASTILLOS Y CONTRATRABES DE CIMENTACION EL PRIMER ESTRIBO SE COLOCARA A 5 CM",
    ],
)
def test_a_first_stirrup_for_a_coordinated_de_cimentacion_is_ambiguous_and_reported(
    tmp_path, texto
):
    r = _con_notas(tmp_path, [f"3. {texto}"])
    assert r.primer_estribo_m == {}
    (aviso,) = r.avisos
    assert "DE CIMENTACION" in aviso and "no se usa" in aviso


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        (
            "EN COLUMNAS Y CONTRATRABES EL PRIMER ESTRIBO SE COLOCARA A 5 CM",
            {"columna": 0.05, "contratrabe": 0.05},
        ),
        (
            "EN COLUMNAS Y VIGAS EL PRIMER ESTRIBO SE COLOCARA A 5 CM",
            {"columna": 0.05, "trabe": 0.05, "contratrabe": 0.05},
        ),
    ],
)
def test_a_first_stirrup_for_a_plain_list_of_families_is_read(tmp_path, texto, esperado):
    r = _con_notas(tmp_path, [f"3. {texto}"])
    assert {f: d.valor for f, d in r.primer_estribo_m.items()} == esperado and r.avisos == []


# Las bases: las nueve de la nota entera, la plantilla y las dos por familia.
_BASES_DE_LA_RONDA = (
    *_NUEVE_BASES,
    (_PL, "SE COLOCARA PLANTILLA DE 8 CM DE ESPESOR"),
    (_P, "EN TRABES EL PRIMER ESTRIBO SE COLOCARA A 5 CM"),
    (_R, "EL RECUBRIMIENTO SERA DE 4 CM EN TRABES"),
)
# 2. Una parte de la estructura detrás de una regla por familia la acota («, EN AZOTEA.»).
_PARTES_DE_LA_ESTRUCTURA = (
    "{f}, EN AZOTEA.",
    "{f}, EN LA AZOTEA.",
    "{f}, EN ENTREPISOS.",
    "{f}, EN LA SUPERESTRUCTURA.",
    "{f}, EN NERVADURAS.",
    "{f}, EN MARCOS.",
    "{f}, EN PILAS.",
    "{f}, EN ELEMENTOS SECUNDARIOS.",
    "{f}, PARA LA SUPERESTRUCTURA.",
    "{f}. EN AZOTEA.",
    "{f}, DE ENTREPISO.",
    "{f}, EN LOSAS Y AZOTEAS.",
)
# 3. Un lugar que no es un elemento conocido también acota (R43: «EN|PARA|APLICA A» y 1–3
# palabras, sin verbo).
_LUGARES_QUE_NO_SE_CONOCEN = (
    "{f}, EN ESCALERAS.",
    "{f}. EN ESCALERAS.",
    "{f}, EN LA CISTERNA.",
    "{f}, EN TANQUES.",
    "{f}, EN MENSULAS Y CAPITELES",
    "{f}, EN VIGUETAS",
    "{f}, EN LOS PRIMEROS NIVELES.",
    "{f}, EN PLANTA BAJA.",
    "{f}, PARA ESCALERAS.",
    "{f}. APLICA A ESCALERAS.",
    "{f}, UNICAMENTE PARA LA CISTERNA.",
    "{f}, EN EL TERCIO MEDIO DEL CLARO.",
    "{f}, FUERA DE ZONAS CONFINADAS.",
    "{f}, SOBRE LA CISTERNA.",
    "{f}, BAJO LA CISTERNA.",
    "{f}, ENTRE EJES A Y C.",
    # lo que dice a qué aplica, o la deja sujeta a algo
    "{f}, EXCLUSIVO DE ESCALERAS.",
    "{f}, VALIDO PARA ESCALERAS.",
    "{f}, ESTA NOTA APLICA EN ESCALERAS.",
    "{f}, CORRESPONDE A ESCALERAS.",
    "{f}, REFERIDO A ESCALERAS.",
    "{f}, CUANDO SE TRATE DE ESCALERAS.",
    "{f}, TRATANDOSE DE ESCALERAS.",
    "{f}, PREVIA AUTORIZACION DEL DIRECTOR.",
    "{f}, SEGUN SE REQUIERA.",
    "{f}, OPCIONALMENTE.",
    "{f}, DE PREFERENCIA.",
    "{f}. ESTE LIMITE PUEDE AUMENTARSE.",
)
# 5. Más maneras de anular una nota.
_MAS_ANULACIONES = (
    "{f}. SE SUSTITUYE POR LA NOTA 9.",
    "{f}. SE REEMPLAZA POR LA NOTA 9.",
    "{f}. ELIMINAR.",
    "{f}. NULA.",
    "{f}. NOTA NULA.",
    "{f}. REVOCADA.",
    "{f}. VER NOTA 9 QUE LA SUSTITUYE.",
    "{f}. VER NOTA 9 QUE LA REEMPLAZA.",
    "{f}. (BORRAR)",
    "{f}. TACHADA.",
    # ronda 2: en pasado, «LA NOTA 9 LA SUSTITUYE», en infinitivo, «QUE SUSTITUYE A ESTA»,
    # «CAMBIA POR»
    "{f}. SE SUSTITUYO POR LA NOTA 9.",
    "{f}. SE REEMPLAZÓ POR LA NOTA 9.",
    "{f}. LA NOTA 9 LA SUSTITUYE.",
    "{f}. LA NOTA 9 LA REEMPLAZA.",
    "{f}. SUSTITUIR POR NOTA 9.",
    "{f}. REEMPLAZAR POR NOTA 9.",
    "{f}. HAY QUE SUSTITUIR ESTA NOTA POR LA NUEVA.",
    "{f}. HAY QUE REEMPLAZAR ESTA NOTA POR LA NUEVA.",
    "{f}. VER NOTA 9 QUE SUSTITUYE A ESTA.",
    "{f}. CAMBIA POR LA NOTA 9.",
    "{f}. SE CANCELO.",
    # ronda 2: «N.A.» suelto, siga lo que siga
    "{f}. N.A. A.",
    "{f}. N.A. B.",
    "{f}. N.A. P.",
    "{f}. N.A. S.P.",
    "{f}. N.A. Y.",
)


@pytest.mark.parametrize(
    ("texto", "campo"),
    [
        pytest.param(envoltura.format(f=frase), regla, id=envoltura.format(f=frase))
        for regla, frase in _BASES_DE_LA_RONDA
        for envoltura in (*_PARTES_DE_LA_ESTRUCTURA, *_LUGARES_QUE_NO_SE_CONOCEN, *_MAS_ANULACIONES)
    ],
)
def test_a_part_of_the_structure_an_unknown_place_or_a_cancellation_never_lets_a_reading_through(
    tmp_path, texto, campo
):
    r = _con_notas(tmp_path, [f"4. {texto}"])
    assert _nada_de_la_nota(r, campo), getattr(r, campo)
    assert r.avisos


@pytest.mark.parametrize(
    ("encabezado", "regla", "frase"),
    [
        pytest.param(encabezado, regla, frase, id=f"{encabezado} {frase}")
        for regla, frase in _BASES_DE_LA_RONDA
        for encabezado in (
            "NOTAS PARA ESCALERAS :",
            "ESCALERAS :",
            "CISTERNA :",
            "TANQUE ELEVADO :",
            "PRECOLADOS :",
            "ESTRUCTURA METALICA :",
            "NOTAS DE PRECOLADOS :",
            # las notas de algo acotan aunque acaben en punto
            "NOTAS PARA ESCALERAS.",
            "NOTAS DE PRECOLADOS.",
        )
    ],
)
def test_a_heading_that_is_neither_generic_nor_a_known_element_scopes_its_notes(
    tmp_path, encabezado, regla, frase
):
    r = _con_notas(tmp_path, [f"1. {frase}"], titulo=encabezado)
    assert _nada_de_la_nota(r, regla), getattr(r, regla)
    assert r.avisos


@pytest.mark.parametrize(
    "encabezado",
    [
        "NOTAS :",
        "NOTAS GENERALES :",
        "NOTAS GENERALES DE ESTRUCTURA.",
        "MATERIALES :",
        "ESPECIFICACIONES :",
        "ESPECIFICACIONES GENERALES :",
        "GENERALES :",
        "CONCRETO :",
        "ACERO :",
        "NOTAS DE CIMENTACION :",
        "CIMENTACION :",
        "NOTAS PARA ELEMENTOS DE CIMENTACION :",
        # los temas de las reglas
        "TRASLAPES :",
        "ANCLAJES Y TRASLAPES :",
        "RECUBRIMIENTOS :",
        "ACERO DE REFUERZO :",
        # el final de un renglón partido que se tomó por encabezado (PRUEBA-1)
        "EN UNA MISMA SECCION.",
        "TOTAL TRANSVERSAL DE LA PIEZA.",
    ],
)
def test_a_generic_heading_or_the_end_of_a_wrapped_line_does_not_scope(tmp_path, encabezado):
    r = _con_notas(tmp_path, [f"1. {_L}"], titulo=encabezado)
    assert r.traslape_max_numero.valor == "6" and r.avisos == []


_DE_CIMENTACION = (
    "NOTAS DE CIMENTACION :",
    "CIMENTACION :",
    "NOTAS PARA ELEMENTOS DE CIMENTACION :",
)


@pytest.mark.parametrize("encabezado", _DE_CIMENTACION)
@pytest.mark.parametrize(
    ("renglon", "campo"),
    [
        ("EL RECUBRIMIENTO SERA DE 4 CM EN TRABES", _R),
        ("EL RECUBRIMIENTO SERA DE 4 CM EN COLUMNAS", _R),
        ("EL RECUBRIMIENTO SERA DE 5 CM EN ZAPATAS Y 4 CM EN TRABES", _R),
        ("EL RECUBRIMIENTO SERA DE 3 CM EN CASTILLOS Y DALAS", _R),
        ("EL RECUBRIMIENTO SERA DE 4 CM EN LOSAS", _R),
        ("EN TRABES EL PRIMER ESTRIBO SE COLOCARA A 5 CM", _P),
        ("EN COLUMNAS EL PRIMER ESTRIBO SE COLOCARA A 5 CM", _P),
    ],
)
def test_under_a_foundation_heading_a_family_that_is_not_foundation_is_reported_not_read(
    tmp_path, encabezado, renglon, campo
):
    r = _con_notas(tmp_path, [f"1. {renglon}"], titulo=encabezado)
    assert _nada_de_la_nota(r, campo), getattr(r, campo)
    assert r.avisos


@pytest.mark.parametrize("encabezado", _DE_CIMENTACION)
@pytest.mark.parametrize(
    ("renglon", "campo", "esperado"),
    [
        (
            "EL RECUBRIMIENTO SERA DE 5 CM EN ZAPATAS Y CONTRATRABES",
            _R,
            {"zapata": 0.05, "contratrabe": 0.05},
        ),
        ("EN CONTRATRABES EL PRIMER ESTRIBO SE COLOCARA A 5 CM", _P, {"contratrabe": 0.05}),
        # los muros de contención son de la cimentación (R42; los muros MC de Marina)
        ("EL RECUBRIMIENTO SERA DE 5 CM EN MUROS DE CONTENCION", _R, {"muro_concreto": 0.05}),
        ("SE COLOCARA PLANTILLA DE CONCRETO POBRE DE 5 CM DE ESPESOR", _PL, 0.05),
        (_L, _T, "6"),
    ],
)
def test_under_a_foundation_heading_foundation_families_and_project_rules_are_read(
    tmp_path, encabezado, renglon, campo, esperado
):
    r = _con_notas(tmp_path, [f"1. {renglon}"], titulo=encabezado)
    if campo == _R:
        leido = {k: d.valor for k, d in r.recubrimiento_m.items() if d.fuente == "nota"}
    elif campo == _P:
        leido = {k: d.valor for k, d in r.primer_estribo_m.items()}
    else:
        leido = getattr(r, campo).valor
    assert leido == esperado and r.avisos == []


def test_marinas_cover_note_under_its_general_heading_keeps_every_cover(tmp_path):
    r = leer_reglas(_marina_notes_and_table(tmp_path), frames=[])
    leidos = {k: d.valor for k, d in r.recubrimiento_m.items() if d.fuente == "nota"}
    assert leidos == {
        "zapata": 0.05,
        "dado": 0.05,
        "pilote": 0.05,
        "contratrabe": 0.05,
        "losa_cimentacion": 0.05,
        "columna": 0.05,
        "trabe": 0.04,
        "losa": 0.04,
        "castillo": 0.03,
        "dala": 0.03,
        "cerramiento": 0.03,
    }


@pytest.mark.parametrize(
    "lista",
    [
        "TRABES Y LOSAS DE AZOTEA",
        "TRABES Y LOSAS DE ENTREPISO",
        "TRABES Y LOSAS DE SOTANO",
        "LOSAS Y TRABES DE AZOTEA",
        "COLUMNAS, TRABES Y LOSAS DE AZOTEA",
    ],
)
def test_a_qualifier_on_the_last_of_a_list_may_be_of_all_of_them_and_is_reported(tmp_path, lista):
    r = _con_notas(tmp_path, [f"4. EL RECUBRIMIENTO SERA DE 4 CM EN {lista}"], titulo="NOTAS :")
    assert _nada_de_la_nota(r, _R), r.recubrimiento_m
    assert r.avisos


def test_concrete_walls_at_the_end_of_a_list_are_still_read(tmp_path):
    r = _con_notas(
        tmp_path,
        ["4. EL RECUBRIMIENTO SERA DE 4 CM EN TRABES Y MUROS DE CONCRETO"],
        titulo="NOTAS :",
    )
    leidos = {k: d.valor for k, d in r.recubrimiento_m.items() if d.fuente == "nota"}
    assert leidos == {"trabe": 0.04, "muro_concreto": 0.04} and r.avisos == []


@pytest.mark.parametrize(
    "texto",
    [
        # lo que acompaña a la otra mitad no vale si la nota también lee lo que niega
        "SE TRASLAPARAN VARILLAS HASTA EL #6, DEL #8 EN ADELANTE SE SOLDARAN, NO SE SOLDARA "
        "NINGUNA",
        "SE TRASLAPARAN VARILLAS HASTA EL #6. DEL #8 EN ADELANTE SE SOLDARAN. NO SE SOLDARA "
        "NINGUNA.",
        "DEL #8 EN ADELANTE SE SOLDARAN, SE TRASLAPARAN VARILLAS HASTA EL #6, SIN TRASLAPES",
        "SE TRASLAPARAN VARILLAS HASTA EL #6, SIN SOLDADURA. DEL #8 EN ADELANTE SE SOLDARAN.",
        "SE TRASLAPARAN VARILLAS HASTA EL #6 Y LAS DEMAS SE SOLDARAN. DEL #10 EN ADELANTE SE "
        "SOLDARAN.",
        "SE TRASLAPARAN VARILLAS HASTA EL #4 Y LAS DEMAS SE SOLDARAN, DEL #8 EN ADELANTE SE "
        "SOLDARAN",
        # ronda 2: «LAS DEMAS SE SOLDARAN» contra «NO SE SOLDARA NINGUNA» o «SIN SOLDADURA»
        "SE PERMITE TRASLAPAR VARILLA HASTA EL #6 Y LAS DEMAS SE SOLDARAN. NO SE SOLDARA NINGUNA.",
        "SE PERMITE TRASLAPAR VARILLA HASTA EL #6, NO SE SOLDARA NINGUNA. LAS DEMAS SE SOLDARAN.",
        "SE PERMITE TRASLAPAR VARILLA HASTA EL #6 Y LAS DEMAS SE SOLDARAN. SIN SOLDADURA.",
        # otro límite para la misma regla, o uno que se encima con el de la otra
        "SE TRASLAPARAN VARILLAS HASTA EL #6. SE PERMITE TRASLAPAR VARILLA HASTA EL #8.",
        "DEL #8 EN ADELANTE SE SOLDARAN. A PARTIR DEL #10 SE SOLDARAN LAS VARILLAS.",
        "SE TRASLAPARAN VARILLAS HASTA EL #8, DEL #8 EN ADELANTE SE SOLDARAN",
        "SE TRASLAPARAN VARILLAS HASTA EL #8, DEL #6 EN ADELANTE SE SOLDARAN",
    ],
)
def test_a_note_that_contradicts_what_it_reads_is_not_used(tmp_path, texto):
    r = _con_notas(tmp_path, [f"4. {texto}"])
    assert r.traslape_max_numero is None and r.soldar_desde_numero is None
    assert r.avisos


def test_two_covers_for_the_same_family_in_one_note_are_not_used(tmp_path):
    r = _con_notas(
        tmp_path, ["4. EL RECUBRIMIENTO SERA DE 4 CM EN TRABES Y 5 CM EN TRABES"], titulo="NOTAS :"
    )
    assert _nada_de_la_nota(r, _R) and r.avisos


@pytest.mark.parametrize("nivel", ["ARRIBA DEL N.A.F.", "SOBRE EL N.A.T.", "BAJO EL N.A.M."])
def test_the_water_table_is_not_a_cancellation(tmp_path, nivel):
    # un nivel («N.A.F.») no anula la nota; pero «ARRIBA DEL N.A.F.» después del espesor es una
    # cláusula corta que lo acota (R49): la nota es un aviso que cita el nivel, no una anulación
    texto = f"2. SE COLOCARA PLANTILLA DE CONCRETO POBRE DE 5 CM DE ESPESOR, {nivel}"
    r = _con_notas(tmp_path, [texto], titulo="NOTAS :")
    assert r.plantilla_espesor_m is None
    (aviso,) = r.avisos
    assert nivel in aviso and "lo niega, lo acota o no se pudo leer" in aviso


@pytest.mark.parametrize(
    "anulacion",
    ["N.A.", "N.A", "N. A.", "(N.A.)", "N/A", "NA.", "N.A. A.", "N.A. S.P.", "N.A. Y."],
)
def test_not_applicable_still_cancels_the_note(tmp_path, anulacion):
    r = _con_notas(tmp_path, [f"4. {_L}. {anulacion}"])
    assert r.traslape_max_numero is None and r.avisos


@pytest.mark.parametrize(
    "texto",
    [
        "SE TRASLAPARAN VARILLAS HASTA 19MM",
        "SE TRASLAPARAN VARILLAS HASTA CAL. 6",
        "SE TRASLAPARAN VARILLAS HASTA EL CAL 6",
        "LAS VARILLAS MAYORES A 19 MM SE SOLDARAN",
        "SE TRASLAPARAN VARILLAS DE DIAMETRO MENOR O IGUAL A 19 MM",
        "SE PERMITE TRASLAPAR VARILLA HASTA EL No . 6",
        "SE PERMITE TRASLAPAR VARILLA HASTA EL No.: 6",
    ],
)
def test_more_diameters_and_odd_bar_marks_are_reported_never_dropped(tmp_path, texto):
    r = _con_notas(tmp_path, [f"4. {texto}"])
    assert r.traslape_max_numero is None and r.soldar_desde_numero is None
    assert r.avisos


def test_a_first_stirrup_said_apart_for_contratrabes_wins_over_the_one_of_trabes(tmp_path):
    texto = (
        "3. EN TRABES EL PRIMER ESTRIBO SE COLOCARA A 5 CM. EN CONTRATRABES EL PRIMER ESTRIBO SE "
        "COLOCARA A 6 CM."
    )
    r = _con_notas(tmp_path, [texto])
    assert {f: d.valor for f, d in r.primer_estribo_m.items()} == {
        "trabe": 0.05,
        "contratrabe": 0.06,
    }
    assert r.avisos == [] and r.contradicciones == []


# --- Task 5b, ronda de arreglos 2 (R44): una cláusula corta sin leer acota o condiciona la regla;
# encabezados con cifras, en minúsculas o «NOTAS PARA …» sin puntuación ----------------------------

# R44: una cláusula corta sin leer que no nombra una familia: la nota es un aviso.
_CLAUSULAS_CORTAS = (
    "{f}. ESCALERAS.",
    "{f}; ESCALERAS",
    "{f}, EDIFICIO B.",
    "{f}, ZONA B.",
    "{f}, EJES A-C.",
    "{f}. HOJA ES-100.",
    "{f}, SI SON ESCALERAS.",
    "{f}, POR SER ESCALERAS.",
    "{f}, COMO MINIMO.",
    "{f}, MINIMO.",
    "{f}, MAXIMO.",
    "{f}, TIPICO.",
    "{f}, PROMEDIO.",
    "{f}, SEGUN.",
    "{f}, SIEMPRE.",
    "{f}, VALIDO.",
)


@pytest.mark.parametrize(
    ("texto", "campo"),
    [
        pytest.param(envoltura.format(f=frase), regla, id=envoltura.format(f=frase))
        for regla, frase in _BASES_DE_LA_RONDA
        for envoltura in _CLAUSULAS_CORTAS
    ]
    + [
        # tras una coma y sin más, la palabra suelta es otra cláusula; en una lista de
        # recubrimientos es un elemento que no se reconoce (ver la prueba de abajo)
        pytest.param(f"{frase}, ESCALERAS.", regla, id=f"{frase}, ESCALERAS.")
        for regla, frase in _BASES_DE_LA_RONDA
        if regla != _R
    ],
)
def test_a_short_unread_clause_never_lets_a_reading_through(tmp_path, texto, campo):
    r = _con_notas(tmp_path, [f"4. {texto}"])
    assert _nada_de_la_nota(r, campo), getattr(r, campo)
    assert r.avisos


def test_a_bare_word_in_a_cover_list_is_an_element_that_is_not_known_and_is_reported(tmp_path):
    r = _con_notas(tmp_path, ["4. EL RECUBRIMIENTO SERA DE 4 CM EN TRABES, ESCALERAS."])
    assert r.recubrimiento_m["trabe"].valor == 0.04
    (aviso,) = r.avisos
    assert "«ESCALERAS»" in aviso and "no se reconoce como un elemento" in aviso


def test_what_another_family_says_with_a_short_clause_now_fails_the_note(tmp_path):
    # Antes (B) la trabe se leía y «COLUMNAS: CINCO» se avisaba aparte; con R44 «CINCO» es una
    # cláusula corta sin leer que no nombra ninguna familia y la nota entera es un aviso: se pierde
    # el 0.04 de las trabes, que era correcto (aceptado: un valor que falta es mejor que uno malo).
    r = _con_notas(tmp_path, ["4. EL RECUBRIMIENTO SERA DE 4 CM EN TRABES. COLUMNAS: CINCO."])
    assert _nada_de_la_nota(r, _R) and r.avisos


@pytest.mark.parametrize("referencia", ["SUSTITUYE A LA NOTA 3.", "DEROGA A LA NOTA 3."])
def test_a_note_that_replaces_another_one_is_read(tmp_path, referencia):
    r = _con_notas(tmp_path, [f"4. {_L}. {referencia}"])
    assert r.traslape_max_numero.valor == "6" and r.avisos == []


@pytest.mark.parametrize(
    "encabezado",
    [
        "NOTAS PARA ESCALERA E-1:",
        "Notas para escaleras:",
        "NOTAS PARA ESCALERAS",
        "notas de precolados",
        "Escalera E-1 :",
    ],
)
def test_a_heading_with_digits_in_any_case_or_notas_para_without_punctuation_scopes(
    tmp_path, encabezado
):
    r = _con_notas(tmp_path, [f"1. {_L}"], titulo=encabezado)
    assert r.traslape_max_numero is None and r.avisos


@pytest.mark.parametrize(
    "encabezado", ["Notas de cimentación", "NOTAS DE CIMENTACION", "Notas generales:"]
)
def test_a_general_or_foundation_heading_in_any_case_is_read_as_such(tmp_path, encabezado):
    r = _con_notas(tmp_path, [f"1. {_L}"], titulo=encabezado)
    assert r.traslape_max_numero.valor == "6" and r.avisos == []
    if "imentaci" in encabezado:
        r = _con_notas(tmp_path, ["1. EL RECUBRIMIENTO SERA DE 4 CM EN TRABES"], titulo=encabezado)
        assert _nada_de_la_nota(r, _R) and r.avisos


@pytest.mark.parametrize("encabezado", ["ESCALERAS", "Escaleras.", "NOTA DE LOSAS ALIGERADAS"])
def test_a_bare_title_without_a_colon_is_not_a_heading(tmp_path, encabezado):
    entidades = _lineas(tmp_path, [f"1. {_L}"], heading=encabezado)
    notas, _ = leer_notas(_textos(entidades), lambda e: "ES-001")
    assert [(n.seccion, n.numero) for n in notas] == [("", 1)]
    r = _con_notas(tmp_path, [f"1. {_L}"], titulo=encabezado)
    assert r.traslape_max_numero.valor == "6" and r.avisos == []


def test_a_heading_keeps_its_digits_and_hyphens(tmp_path):
    entidades = _lineas(tmp_path, [f"1. {_L}"], heading="NOTAS PARA ESCALERA E-1:")
    notas, _ = leer_notas(_textos(entidades), lambda e: "ES-001")
    assert [(n.seccion, n.encabezado) for n in notas] == [
        ("NOTAS PARA ESCALERA E-1", "NOTAS PARA ESCALERA E-1:")
    ]


# --- Task 5c (R46): una cláusula corta con marca o puntuación tampoco deja pasar la regla, una
# anulación sin «SE», y un encabezado que acota sigue acotando bajo los subencabezados generales --

# 1. Una cláusula corta cuya primera palabra trae cifras («T-1», «E1», «MC-1») o que trae
# puntuación («S/N», «ESCALERAS*», «[ESCALERAS]», «ESCALERAS / RAMPAS», «ZONA 'A'»): acota o
# condiciona la regla igual que «ESCALERAS».
_CLAUSULAS_CON_MARCA = (
    "T-1",
    "C-1 Y C-2",
    "MC-1",
    "Z-1",
    "E1",
    "N-1",
    "E-1",
    "ESC-1",
    "ZONA 'A'",
    "S/N",
    "ESCALERAS*",
    "[ESCALERAS]",
    "ESCALERAS -",
    "- ESCALERAS",
    "ESCALERAS / RAMPAS",
    "ESCALERAS+RAMPAS",
    "ESCALERAS & RAMPAS",
    # de cuatro palabras y con la marca al empezar o al acabar; y con la cifra al empezar
    "- EDIFICIO B NIVEL 3",
    "EDIFICIO B NIVEL 3 -",
    "*EDIFICIO B NIVEL 3*",
    "3ER NIVEL",
    "1A",
    # R48: paréntesis dentro de la cláusula y más marcas dentro de las palabras
    "ESCALERAS (E-1)",
    "ZONA (A)",
    "ESCALERA (TIPO)",
    "ESCALERA E-1 (CUERPO B)",
    "ESCALERAS (VER E-1)",
    "(ESCALERAS)",
    "ESC#1",
    "ESC=1",
    "ESCALERAS Ø",
    "ESCALERAS 100%",
    "TIPO#A",
    "#ESC",
    "ESC(1)",
    "*(ESCALERAS) *",
    # R49: cualquier carácter que no sea un espacio
    "ESCALERAS~",
    "~ESCALERAS",
    "ESCALERAS…",
    "ESCALERAS?",
    "ESCALERAS!",
    "E-1 @ E-4",
    "ESCALERAS @ E-1",
    "N.P.T.",
    "P.B.",
    "P.A.",
    "ESC. A",
    "<ESCALERAS>",
    "ESCALERAS^",
    "ESCALERAS|RAMPAS",
    "ESCALERAS_E1",
    "ESCALERAS§",
)
_ENVOLTURAS_DE_LA_CLAUSULA = ("{f}. {c}.", "{f}, {c}.", "{f}; {c}")


@pytest.mark.parametrize(
    ("texto", "campo"),
    [
        pytest.param(
            envoltura.format(f=frase, c=clausula), regla, id=envoltura.format(f=frase, c=clausula)
        )
        for regla, frase in [
            *_BASES_DE_LA_RONDA,
            (_R, "EL RECUBRIMIENTO LIBRE SERA DE 4 CM EN TRABES"),
        ]
        for envoltura in _ENVOLTURAS_DE_LA_CLAUSULA
        for clausula in _CLAUSULAS_CON_MARCA
    ],
)
def test_a_short_unread_clause_with_a_mark_or_punctuation_never_lets_a_reading_through(
    tmp_path, texto, campo
):
    r = _con_notas(tmp_path, [f"4. {texto}"])
    assert _nada_de_la_nota(r, campo), getattr(r, campo)
    assert r.avisos


@pytest.mark.parametrize("neutra", ["VER DETALLE 3", "RESPECTIVAMENTE"])
def test_a_neutral_short_clause_is_still_read_past(tmp_path, neutra):
    r = _con_notas(tmp_path, [f"4. {_L}, {neutra}."])
    assert r.traslape_max_numero.valor == "6" and r.avisos == []
    # en una lista de recubrimientos «RESPECTIVAMENTE» sobra y se avisa, pero el valor se lee
    r = _con_notas(tmp_path, [f"4. EL RECUBRIMIENTO LIBRE SERA DE 4 CM EN TRABES, {neutra}."])
    assert r.recubrimiento_m["trabe"].valor == 0.04 and r.recubrimiento_m["trabe"].fuente == "nota"


# 2. Una nota que se anula sin decir «SE …»: «VER NOTA 9 QUE LA SUSTITUYO», «LA NOTA 9 SUSTITUYE
# ESTA».
_ANULACIONES_SIN_SE = (
    "{f}. VER NOTA 9 QUE LA SUSTITUYO.",
    "{f}. VER NOTA 9 QUE LA SUSTITUYÓ.",
    "{f}. VER NOTA 9 QUE LA REEMPLAZO.",
    "{f}. VER NOTA 9 QUE LA ANULO.",
    "{f}. VER NOTA 9 QUE LA CANCELO.",
    "{f}. VER NOTA 9 QUE LA DEROGO.",
    "{f}. LA NOTA 9 SUSTITUYE ESTA.",
    "{f}. LA NOTA 9 REEMPLAZA ESTA.",
    "{f}. LA NOTA 9 ANULA ESTA.",
    "{f}. LA NOTA 9 CANCELA ESTA.",
    "{f}. LA NOTA 9 DEROGA ESTA.",
    "{f}. LA NOTA 9 SUSTITUYE A ESTA.",
    "{f}. LA NOTA 9 CANCELA A ESTA.",
)


@pytest.mark.parametrize(
    ("texto", "campo"),
    [
        pytest.param(envoltura.format(f=frase), regla, id=envoltura.format(f=frase))
        for regla, frase in _BASES_DE_LA_RONDA
        for envoltura in _ANULACIONES_SIN_SE
    ],
)
def test_a_note_cancelled_by_another_one_without_se_never_lets_a_reading_through(
    tmp_path, texto, campo
):
    r = _con_notas(tmp_path, [f"4. {texto}"])
    assert _nada_de_la_nota(r, campo), getattr(r, campo)
    assert r.avisos


@pytest.mark.parametrize(
    "referencia",
    [
        "SUSTITUYE A LA NOTA 3.",
        "DEROGA A LA NOTA 3.",
        "REEMPLAZA A LA NOTA 3.",
        "CANCELA A LA NOTA 3.",
        "ANULA A LA NOTA 3.",
        "ESTA NOTA SUSTITUYE A LA NOTA 3.",
        "ESTA NOTA REEMPLAZA A LA NOTA 3.",
    ],
)
def test_a_note_that_replaces_another_one_is_still_read(tmp_path, referencia):
    r = _con_notas(tmp_path, [f"4. {_L}. {referencia}"])
    assert r.traslape_max_numero.valor == "6" and r.avisos == []


# 3. Un encabezado que acota sigue acotando bajo un subencabezado general.
_SUBENCABEZADOS_GENERALES = (
    "Refuerzo:",
    "Notas:",
    "Proyecto:",
    "Obra:",
    "Observaciones:",
    "Traslapes:",
    "NOTAS DE REFUERZO",
    "NOTAS DEL PROYECTO",
    "REFUERZO :",
    "NOTAS :",
)
_ENCABEZADOS_QUE_ACOTAN_5C = ("NOTAS PARA ESCALERAS :", "ESCALERAS :", "COLUMNAS :")


def _con_encabezados(tmp_path, encabezados, renglones):
    """``renglones`` bajo el último de ``encabezados``: van uno bajo otro en la misma columna."""
    grupos = [(h, []) for h in encabezados[:-1]] + [(encabezados[-1], renglones)]
    return leer_reglas(_dibujo(tmp_path, tabla=False, bloques=[(grupos, 1)]), frames=[])


@pytest.mark.parametrize(
    ("alto", "bajo", "regla", "frase"),
    [
        pytest.param(alto, bajo, regla, frase, id=f"{alto} > {bajo} > {frase}")
        for regla, frase in _BASES_DE_LA_RONDA
        for alto in _ENCABEZADOS_QUE_ACOTAN_5C
        for bajo in _SUBENCABEZADOS_GENERALES
    ],
)
def test_a_general_subheading_never_clears_an_outer_scoping_heading(
    tmp_path, alto, bajo, regla, frase
):
    r = _con_encabezados(tmp_path, [alto, bajo], [f"1. {frase}"])
    assert _nada_de_la_nota(r, regla), getattr(r, regla)
    assert r.avisos


@pytest.mark.parametrize(
    "bajos", [("Refuerzo:", "NOTAS DE REFUERZO"), ("Notas:", "Obra:", "Proyecto:")]
)
def test_several_general_subheadings_still_keep_the_outer_scope(tmp_path, bajos):
    r = _con_encabezados(tmp_path, ["NOTAS PARA ESCALERAS :", *bajos], [f"1. {_L}"])
    assert r.traslape_max_numero is None and r.avisos


def test_the_outer_scope_is_still_the_scope_the_rule_is_read_in(tmp_path):
    # «COLUMNAS :» sigue acotando bajo «Refuerzo:»: un recubrimiento de columnas se lee; un primer
    # estribo que dice sus elementos, también, dentro de lo que el encabezado acota.
    r = _con_encabezados(
        tmp_path, ["COLUMNAS :", "Refuerzo:"], ["1. EL RECUBRIMIENTO SERA DE 5 CM EN COLUMNAS"]
    )
    assert (
        r.recubrimiento_m["columna"].valor == 0.05 and r.recubrimiento_m["columna"].fuente == "nota"
    )
    r = _con_encabezados(
        tmp_path, ["TRABES :", "Refuerzo:"], ["1. EN TRABES EL PRIMER ESTRIBO SE COLOCARA A 5 CM"]
    )
    assert sorted(r.primer_estribo_m) == ["contratrabe", "trabe"] and r.avisos == []


def test_a_top_level_general_heading_ends_the_scope(tmp_path):
    # El reinicio: «NOTAS GENERALES DE ESTRUCTURA» (el encabezado de las generales de todo el
    # proyecto) cierra lo que acotaba un encabezado de arriba.
    for encabezados in (
        ["NOTAS PARA ESCALERAS :", "NOTAS GENERALES DE ESTRUCTURA."],
        ["NOTAS PARA ESCALERAS :", "NOTAS GENERALES DE ESTRUCTURA.", "REFUERZO :"],
        ["ESCALERAS :", "Notas generales de estructura", "MATERIALES :", "REFUERZO :"],
    ):
        r = _con_encabezados(tmp_path, encabezados, [f"1. {_L}"])
        assert r.traslape_max_numero.valor == "6" and r.avisos == [], encabezados


def test_no_heading_above_means_no_scope(tmp_path):
    r = _con_encabezados(tmp_path, ["Refuerzo:", "Notas:"], [f"1. {_L}"])
    assert r.traslape_max_numero.valor == "6" and r.avisos == []


@pytest.mark.parametrize("bajo", ["Refuerzo:", "Notas:", "REFUERZO :"])
def test_a_foundation_heading_keeps_its_restriction_under_a_general_subheading(tmp_path, bajo):
    r = _con_encabezados(
        tmp_path, ["NOTAS DE CIMENTACION", bajo], ["1. EL RECUBRIMIENTO SERA DE 4 CM EN TRABES"]
    )
    assert _nada_de_la_nota(r, _R) and r.avisos
    r = _con_encabezados(tmp_path, ["NOTAS DE CIMENTACION", bajo], [f"1. {_L}"])
    assert r.traslape_max_numero.valor == "6" and r.avisos == []


def test_a_note_under_a_scoped_block_in_one_sheet_and_a_general_one_in_another_is_reported(
    tmp_path,
):
    # La misma nota, igual, en dos columnas: bajo «ESCALERAS :» en una y sin encabezado de arriba
    # en la otra. Una `Nota` con las dos maneras; la que acota manda (nunca se lee en silencio).
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for k, grupos in enumerate(
        (
            [("REFUERZO :", [f"1. {_L}"])],
            [("ESCALERAS :", []), ("REFUERZO :", [f"1. {_L}"])],
        )
    ):
        bloque = doc.blocks.new(f"NOTAS_{k}")
        _escribir_notas(bloque, grupos)
        msp.add_blockref(f"NOTAS_{k}", (50.0 + 100.0 * k, 40.0))
    ruta = tmp_path / "dos.dxf"
    doc.saveas(ruta)
    entidades = DxfParser().parse_file(ruta).entities
    notas, contradicciones = leer_notas(_textos(entidades), lambda e: "ES-001")
    (nota,) = notas
    assert nota.copias == 2 and contradicciones == []
    assert sorted(nota.cadenas) == [["REFUERZO :"], ["REFUERZO :", "ESCALERAS :"]]
    r = leer_reglas(entidades, frames=[])
    assert r.traslape_max_numero is None and r.avisos


def test_a_note_keeps_the_headings_above_it_nearest_first(tmp_path):
    entidades = _notas_dxf(tmp_path, [("NOTAS PARA ESCALERAS :", []), ("Refuerzo:", [f"1. {_L}"])])
    (nota,) = leer_notas(_textos(entidades), lambda e: "ES-001")[0]
    assert (nota.seccion, nota.encabezado) == ("Refuerzo", "Refuerzo:")
    assert nota.cadenas == [["Refuerzo:", "NOTAS PARA ESCALERAS :"]]


def test_a_first_stirrup_without_elements_does_not_take_them_from_a_heading_above_a_subheading(
    tmp_path,
):
    # Directamente bajo «TRABES :» el primer estribo sin elementos es el de las trabes; bajo un
    # subencabezado general no se sabe si éste sigue siendo ese bloque o es uno general que viene
    # después: no se toman los elementos del encabezado de arriba, la nota es un aviso.
    renglon = ["1. EL PRIMER ESTRIBO SE COLOCARA A 5 CM"]
    r = _con_encabezados(tmp_path, ["TRABES :"], renglon)
    assert {f: d.valor for f, d in r.primer_estribo_m.items()} == {
        "trabe": 0.05,
        "contratrabe": 0.05,
    }
    for sub in ("Refuerzo:", "Notas:", "REFUERZO :"):
        r = _con_encabezados(tmp_path, ["TRABES :", sub], renglon)
        assert r.primer_estribo_m == {} and r.avisos
        # … pero uno que dice sus elementos se lee, dentro de lo que el encabezado acota
        r = _con_encabezados(
            tmp_path, ["TRABES :", sub], ["1. EN TRABES EL PRIMER ESTRIBO SE COLOCARA A 5 CM"]
        )
        assert sorted(r.primer_estribo_m) == ["contratrabe", "trabe"] and r.avisos == []


def _con_dos_columnas(tmp_path, encabezados_a, encabezados_b, renglon):
    """La misma nota, igual, en dos columnas, ambas bajo «REFUERZO :» y cada una con sus
    encabezados de arriba."""
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for k, arriba in enumerate((encabezados_a, encabezados_b)):
        grupos = [(h, []) for h in arriba] + [("REFUERZO :", [renglon])]
        bloque = doc.blocks.new(f"NOTAS_{k}")
        _escribir_notas(bloque, grupos)
        msp.add_blockref(f"NOTAS_{k}", (50.0 + 100.0 * k, 40.0))
    ruta = tmp_path / "dos.dxf"
    doc.saveas(ruta)
    return leer_reglas(DxfParser().parse_file(ruta).entities, frames=[])


@pytest.mark.parametrize(
    ("arriba_a", "arriba_b"),
    [
        # una copia está bajo un encabezado que acota y la otra no
        (["COLUMNAS :"], []),
        # cada una está bajo uno que acota a otra cosa
        (["COLUMNAS :"], ["TRABES :"]),
    ],
)
def test_copies_of_a_note_under_different_scopes_are_not_read(tmp_path, arriba_a, arriba_b):
    # El recubrimiento de columnas es de la nota; lo que no se sabe es si una de las copias lo
    # acota a otra cosa: no se lee.
    r = _con_dos_columnas(
        tmp_path, arriba_a, arriba_b, "1. EL RECUBRIMIENTO SERA DE 5 CM EN COLUMNAS"
    )
    assert _nada_de_la_nota(r, _R) and r.avisos


# --- Task 5c, R47: un encabezado que acota bajo otro que acota es ambiguo («NOTAS PARA ESCALERAS :»
# y debajo «COLUMNAS :» pueden ser las columnas de la escalera): las notas de abajo son un aviso ---

_ENCABEZADOS_QUE_ACOTAN_ANIDADOS = (
    ("NOTAS PARA ESCALERAS :", "COLUMNAS :"),
    ("COLUMNAS :", "NOTAS PARA ESCALERAS :"),
    ("ESCALERAS :", "NOTAS PARA TRABES :"),
    ("NOTAS PARA TRABES :", "ESCALERAS :"),
    ("COLUMNAS :", "TRABES :"),
    ("TRABES :", "COLUMNAS :"),
    ("ESCALERAS :", "CISTERNA :"),
)
# la regla, su frase y el elemento que el encabezado de adentro acotaría si estuviera solo
_LO_QUE_EL_ENCABEZADO_DE_ADENTRO_LEERIA = (
    (_R, "EL RECUBRIMIENTO SERA DE 5 CM EN COLUMNAS"),
    (_R, "EL RECUBRIMIENTO SERA DE 4 CM EN TRABES"),
    (_P, "EN TRABES EL PRIMER ESTRIBO SE COLOCARA A 5 CM"),
    (_P, "EL PRIMER ESTRIBO SE COLOCARA A 5 CM"),
    *_NUEVE_BASES,
)


@pytest.mark.parametrize(
    ("arriba", "regla", "frase"),
    [
        pytest.param(arriba, regla, frase, id=f"{' > '.join(arriba)} > {frase}")
        for arriba in _ENCABEZADOS_QUE_ACOTAN_ANIDADOS
        for regla, frase in _LO_QUE_EL_ENCABEZADO_DE_ADENTRO_LEERIA
    ],
)
def test_a_scoping_heading_nested_under_another_one_is_ambiguous_and_reported(
    tmp_path, arriba, regla, frase
):
    r = _con_encabezados(tmp_path, list(arriba), [f"1. {frase}"])
    assert _nada_de_la_nota(r, regla), getattr(r, regla)
    assert r.avisos


@pytest.mark.parametrize("entre", [[], ["Refuerzo:"], ["Notas:", "NOTAS DE REFUERZO"]])
def test_a_general_subheading_between_two_scoping_headings_changes_nothing(tmp_path, entre):
    for arriba in (
        ["NOTAS PARA ESCALERAS :", *entre, "COLUMNAS :"],
        ["COLUMNAS :", *entre, "ESCALERAS :"],
    ):
        r = _con_encabezados(tmp_path, arriba, ["1. EL RECUBRIMIENTO SERA DE 5 CM EN COLUMNAS"])
        assert _nada_de_la_nota(r, _R) and r.avisos, arriba


def test_the_aviso_of_a_nested_scoping_heading_names_the_inner_one(tmp_path):
    r = _con_encabezados(
        tmp_path,
        ["NOTAS PARA ESCALERAS :", "COLUMNAS :"],
        ["1. EL RECUBRIMIENTO SERA DE 5 CM EN COLUMNAS"],
    )
    (aviso,) = r.avisos
    assert "COLUMNAS" in aviso and "lo niega, lo acota o no se pudo leer" in aviso


@pytest.mark.parametrize(
    "arriba",
    [
        ["NOTAS GENERALES DE ESTRUCTURA.", "COLUMNAS :"],
        ["NOTAS GENERALES DE ESTRUCTURA.", "REFUERZO :", "COLUMNAS :"],
        ["NOTAS GENERALES DE ESTRUCTURA.", "MATERIALES :", "REFUERZO :", "COLUMNAS :"],
        ["Refuerzo:", "COLUMNAS :"],
        # «NOTAS GENERALES DE ESTRUCTURA» cierra lo que acotaba uno de más arriba
        ["NOTAS PARA ESCALERAS :", "NOTAS GENERALES DE ESTRUCTURA.", "COLUMNAS :"],
        ["ESCALERAS :", "NOTAS GENERALES DE ESTRUCTURA.", "REFUERZO :", "COLUMNAS :"],
    ],
)
def test_a_scoping_heading_under_the_general_notes_heading_still_reads_per_family(tmp_path, arriba):
    r = _con_encabezados(tmp_path, arriba, ["1. EL RECUBRIMIENTO SERA DE 5 CM EN COLUMNAS"])
    assert r.recubrimiento_m["columna"].valor == 0.05
    assert r.recubrimiento_m["columna"].fuente == "nota" and r.avisos == []
    # … y acota: una regla de todo el proyecto no se lee, un recubrimiento de otro elemento tampoco
    r = _con_encabezados(tmp_path, arriba, [f"1. {_L}"])
    assert r.traslape_max_numero is None and r.avisos
    r = _con_encabezados(tmp_path, arriba, ["1. EL RECUBRIMIENTO SERA DE 4 CM EN TRABES"])
    assert _nada_de_la_nota(r, _R) and r.avisos


def test_a_first_stirrup_under_a_scoping_heading_under_the_general_notes_still_takes_its_elements(
    tmp_path,
):
    r = _con_encabezados(
        tmp_path,
        ["NOTAS GENERALES DE ESTRUCTURA.", "TRABES :"],
        ["1. EL PRIMER ESTRIBO SE COLOCARA A 5 CM"],
    )
    assert {f: d.valor for f, d in r.primer_estribo_m.items()} == {
        "trabe": 0.05,
        "contratrabe": 0.05,
    }
    assert r.avisos == []


# --- Task 5c, R48: un bloque de notas acaba donde otra cosa empieza. Un encabezado de un bloque de
# arriba no es el de las notas de otro bloque: ni da los elementos de un primer estribo ni acota ---

_PE = "EL PRIMER ESTRIBO SE COLOCARA A 5 CM DEL PAÑO"
_RC = "EL RECUBRIMIENTO SERA DE 4 CM EN COLUMNAS"


def _apilar(*bloques, paso=0.22):
    """Los bloques ``(titulo | None, renglones, hueco)`` uno bajo otro en la misma columna, como
    renglones ``(texto, y, alto)``: ``hueco`` es el espacio en blanco antes del bloque."""
    y = 0.0
    lineas = []
    for titulo, renglones, hueco in bloques:
        y -= hueco
        if titulo is not None:
            lineas.append((titulo, y, 0.14))
            y -= paso * 1.2
        for renglon in renglones:
            texto, dx = (renglon, 0.0) if isinstance(renglon, str) else renglon
            lineas.append((texto, y, 0.10, dx))
            y -= paso
    return lineas


def _entidades_de(tmp_path, lineas):
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for texto, y, alto, *dx in lineas:
        msp.add_text(texto, height=alto).set_placement((dx[0] if dx else 0.0, y))
    ruta = tmp_path / "columna.dxf"
    doc.saveas(ruta)
    return DxfParser().parse_file(ruta).entities


def _con_bloques(tmp_path, *bloques):
    return leer_reglas(_entidades_de(tmp_path, _apilar(*bloques)), frames=[])


def _estribos(r):
    return {f: d.valor for f, d in r.primer_estribo_m.items()}


# Los casos del revisor (bloques de 60 unidades de distancia, el de abajo sin encabezado que se
# reconozca): el primer estribo del bloque de abajo no es el de «COLUMNAS :».
@pytest.mark.parametrize(
    "titulo",
    [
        None,
        "Notas generales",
        "NOTAS GENERALES",
        "NOTAS",
        "ESPECIFICACIONES GENERALES",
        "GENERALIDADES",
    ],
)
def test_a_far_block_without_a_known_heading_does_not_inherit_the_elements_above(tmp_path, titulo):
    de_arriba = [("COLUMNAS :", ["1. EL CONCRETO SERA F'C=250 KG/CM2"])]
    de_abajo = [(titulo, [f"1. {_PE}", "2. LAS COTAS RIGEN AL DIBUJO"])]
    r = leer_reglas(
        _dibujo(tmp_path, tabla=False, bloques=[(de_arriba, 1), (de_abajo, 1)]), frames=[]
    )
    assert r.primer_estribo_m == {} and r.avisos


def test_the_reviewers_far_block_cases(tmp_path):
    def con(*bloques):
        return leer_reglas(
            _dibujo(tmp_path, tabla=False, bloques=[(b, 1) for b in bloques]), frames=[]
        )

    columnas = [("COLUMNAS :", [f"1. {_RC}"])]
    # sin encabezado, o con uno que no se reconoce: el recubrimiento de arriba se lee, el primer
    # estribo de abajo no
    for titulo in (None, "Notas generales"):
        r = con(columnas, [(titulo, [f"2. {_PE}"])])
        assert r.recubrimiento_m["columna"].valor == 0.04 and r.primer_estribo_m == {}
        assert r.avisos
    # R50: el alcance sólo crece hacia abajo; un encabezado general de otro bloque no cierra lo que
    # acota uno de arriba (sí «NOTAS GENERALES DE ESTRUCTURA», el de las generales del proyecto)
    escaleras = [("NOTAS PARA ESCALERAS :", ["1. CONCRETO F'C=250"])]
    r = con(escaleras, [("NOTAS GENERALES :", [f"1. {_L}"])])
    assert r.traslape_max_numero is None and r.avisos
    r = con(escaleras, [("NOTAS GENERALES DE ESTRUCTURA", [f"1. {_L}"])])
    assert r.traslape_max_numero.valor == "6" and r.avisos == []
    # … y uno que acota bajo otro que acota es ambiguo (R47), lejos o cerca
    r = con(escaleras, [("COLUMNAS :", [f"1. {_RC}", f"2. {_PE}"])])
    assert _nada_de_la_nota(r, _R) and r.primer_estribo_m == {} and r.avisos
    # … y un encabezado de cimentación de arriba sigue restringiendo a las familias de abajo
    r = con([("NOTAS DE CIMENTACION", [])], [("COLUMNAS :", [f"1. {_RC}", f"2. {_PE}"])])
    assert _nada_de_la_nota(r, _R) and r.primer_estribo_m == {} and r.avisos
    # … y uno de cimentación lo sigue siendo para las notas de su bloque
    r = con([("COLUMNAS :", [])], [("NOTAS DE CIMENTACION", [f"1. {_RC}", f"2. {_PE}"])])
    assert _nada_de_la_nota(r, _R) and r.primer_estribo_m == {} and r.avisos
    # lo que está dentro de un mismo bloque no cambia
    r = con([("COLUMNAS :", []), ("REFUERZO :", [f"1. {_RC}"])])
    assert r.recubrimiento_m["columna"].valor == 0.04 and r.avisos == []
    r = con([("TRABES :", [f"1. {_PE}"])])
    assert _estribos(r) == {"trabe": 0.05, "contratrabe": 0.05}
    r = con([("TRABES :", []), ("TRABES :", [f"1. {_PE}"])])
    assert r.primer_estribo_m == {} and r.avisos


# Cada manera de saber que un bloque acabó, sola y pegada al bloque de arriba (sin los 60 de
# distancia): el de abajo ni toma los elementos del encabezado de arriba ni queda acotado por él.
_ARRIBA_DE_COLUMNAS = (
    "COLUMNAS :",
    ["1. EL CONCRETO SERA F'C=250 KG/CM2", "2. LAS COTAS RIGEN"],
    0.0,
)
_BLOQUES_APARTE = [
    pytest.param(
        # la numeración empieza de nuevo sin un encabezado que lo explique
        (None, [f"1. {_PE}"], 0.44),
        id="la numeracion empieza de nuevo",
    ),
    pytest.param(
        # un renglón más alto que el texto y que no es un encabezado que se reconozca
        ("Notas generales", [f"3. {_PE}"], 0.44),
        id="un titulo que no se reconoce",
    ),
    pytest.param(
        # un hueco de más de tres renglones antes de las notas
        (None, [f"3. {_PE}"], 1.4),
        id="un hueco de mas de tres renglones",
    ),
]


@pytest.mark.parametrize("de_abajo", _BLOQUES_APARTE)
def test_each_block_boundary_alone_stops_the_elements_from_the_heading_above(tmp_path, de_abajo):
    r = _con_bloques(tmp_path, _ARRIBA_DE_COLUMNAS, de_abajo)
    assert r.primer_estribo_m == {} and r.avisos
    # … y la nota de abajo no tiene encabezado propio: el de arriba queda más allá del límite, en
    # la cadena, donde sigue acotando (R50)
    entidades = _entidades_de(tmp_path, _apilar(_ARRIBA_DE_COLUMNAS, de_abajo))
    notas, _ = leer_notas(_textos(entidades), lambda e: "ES-001")
    (abajo,) = [n for n in notas if "ESTRIBO" in n.texto]
    assert (abajo.seccion, abajo.encabezado) == ("", "")
    assert abajo.cadenas == [[LIMITE_DE_BLOQUE, "COLUMNAS :"]]


@pytest.mark.parametrize("de_abajo", _BLOQUES_APARTE)
def test_a_block_without_a_heading_under_a_scoping_block_is_ambiguous(tmp_path, de_abajo):
    # R49: un límite de bloque nunca vuelve sin acotar una nota que estaba acotada: el bloque de
    # abajo no tiene encabezado propio y arriba hay uno que acota, así que no se sabe a qué va
    arriba = ("NOTAS PARA ESCALERAS :", ["1. CONCRETO F'C=250", "2. LAS COTAS RIGEN"], 0.0)
    titulo, renglones, hueco = de_abajo
    abajo = (titulo, [renglones[0].replace(_PE, _L)], hueco)
    r = _con_bloques(tmp_path, arriba, abajo)
    assert r.traslape_max_numero is None and r.avisos


@pytest.mark.parametrize(
    "de_abajo",
    [
        # sin un límite, el encabezado de arriba sigue siendo el del bloque
        pytest.param((None, [f"3. {_PE}"], 0.44), id="la numeracion sigue"),
        pytest.param((None, [f"3. {_PE}"], 0.4), id="un hueco de menos de tres renglones"),
    ],
)
def test_without_a_block_boundary_the_heading_above_is_still_the_one_of_the_note(
    tmp_path, de_abajo
):
    arriba = ("TRABES :", ["1. CONCRETO F'C=250", "2. LAS COTAS RIGEN"], 0.0)
    r = _con_bloques(tmp_path, arriba, de_abajo)
    assert _estribos(r) == {"trabe": 0.05, "contratrabe": 0.05} and r.avisos == []


def test_a_sub_heading_with_its_own_numbering_does_not_end_the_block_above(tmp_path):
    # «Refuerzo:» es un encabezado que se reconoce: explica que la numeración empiece de nuevo
    r = _con_bloques(
        tmp_path,
        ("NOTAS PARA ESCALERAS :", ["1. CONCRETO F'C=250", "2. LAS COTAS RIGEN"], 0.0),
        ("Refuerzo:", [f"1. {_L}"], 0.44),
    )
    assert r.traslape_max_numero is None and r.avisos


def test_the_notes_of_a_block_keep_the_heading_of_their_own_block(tmp_path):
    entidades = _entidades_de(
        tmp_path,
        _apilar(
            ("NOTAS PARA ESCALERAS :", ["1. CONCRETO F'C=250", "2. LAS COTAS RIGEN"], 0.0),
            ("REFUERZO :", [f"1. {_L}", "2. LAS COTAS RIGEN"], 0.44),
        ),
    )
    notas, _ = leer_notas(_textos(entidades), lambda e: "ES-001")
    assert sorted((n.seccion, n.numero) for n in notas) == [
        ("NOTAS PARA ESCALERAS", 1),
        ("NOTAS PARA ESCALERAS", 2),
        ("REFUERZO", 1),
        ("REFUERZO", 2),
    ]


def test_an_unknown_subtitle_right_under_a_heading_does_not_end_its_block(tmp_path):
    # «Notas generales» (más alto que el texto, sin «:») cuelga de «NOTAS PARA ESCALERAS :», que no
    # tiene notas propias: las de abajo siguen acotadas por él
    r = _con_bloques(
        tmp_path,
        ("NOTAS PARA ESCALERAS :", [], 0.0),
        ("Notas generales", [f"1. {_L}"], 0.0),
    )
    assert r.traslape_max_numero is None and r.avisos
    # … y no se sabe si el subtítulo cambia de qué elementos es el primer estribo: no se toman
    # los del encabezado de arriba
    r = _con_bloques(tmp_path, ("TRABES :", [], 0.0), ("Detalles", [f"1. {_PE}"], 0.0))
    assert r.primer_estribo_m == {} and r.avisos
    r = _con_bloques(tmp_path, ("TRABES :", [f"1. {_PE}"], 0.0))
    assert _estribos(r) == {"trabe": 0.05, "contratrabe": 0.05}


def test_the_chain_of_a_note_keeps_an_unknown_subtitle_but_the_section_is_the_heading(tmp_path):
    entidades = _entidades_de(
        tmp_path,
        _apilar(("NOTAS PARA ESCALERAS :", [], 0.0), ("Notas generales", [f"1. {_L}"], 0.0)),
    )
    (nota,) = leer_notas(_textos(entidades), lambda e: "ES-001")[0]
    assert (nota.seccion, nota.encabezado) == ("NOTAS PARA ESCALERAS", "NOTAS PARA ESCALERAS :")
    assert nota.cadenas == [["Notas generales", "NOTAS PARA ESCALERAS :"]]


def test_a_numbering_that_starts_again_at_the_same_number_also_ends_the_block(tmp_path):
    # el bloque de arriba tiene una sola nota, la 1: la «1.» de abajo no sigue a ninguna
    r = _con_bloques(
        tmp_path,
        ("COLUMNAS :", ["1. CONCRETO F'C=250 KG/CM2"], 0.0),
        (None, [f"1. {_PE}"], 0.44),
    )
    assert r.primer_estribo_m == {} and r.avisos


# --- Task 5c, R49: un límite de bloque nunca vuelve sin acotar una nota acotada -----------------

_UN_HUECO_COMO_UNA_FIGURA = 1.4


@pytest.mark.parametrize(
    "encabezado", ["COLUMNAS :", "NOTAS PARA ESCALERAS :", "CISTERNA :", "ESCALERAS :"]
)
@pytest.mark.parametrize(
    ("regla", "frase"),
    [
        (_T, _L),
        (_R, "EL RECUBRIMIENTO SERA DE 4 CM EN TRABES"),
        (_PL, "SE COLOCARA PLANTILLA DE 8 CM DE ESPESOR"),
        (_P, "EN TRABES EL PRIMER ESTRIBO SE COLOCARA A 5 CM"),
        (_P, "EL PRIMER ESTRIBO SE COLOCARA A 5 CM"),
    ],
)
def test_notes_after_a_gap_under_a_scoping_heading_are_not_read_as_the_projects(
    tmp_path, encabezado, regla, frase
):
    # el encabezado, un hueco del tamaño de una figura y las notas: el encabezado sigue acotando
    r = _con_bloques(
        tmp_path, (encabezado, [], 0.0), (None, [f"1. {frase}"], _UN_HUECO_COMO_UNA_FIGURA)
    )
    assert _nada_de_la_nota(r, regla), getattr(r, regla)
    assert r.avisos


@pytest.mark.parametrize(
    "encabezado", ["REFUERZO :", "NOTAS :", "MATERIALES :", "NOTAS GENERALES DE ESTRUCTURA."]
)
def test_notes_after_a_gap_under_a_generic_heading_are_read(tmp_path, encabezado):
    r = _con_bloques(
        tmp_path, (encabezado, [], 0.0), (None, [f"1. {_L}"], _UN_HUECO_COMO_UNA_FIGURA)
    )
    assert r.traslape_max_numero.valor == "6" and r.avisos == []
    # … y sin ningún encabezado arriba
    r = _con_bloques(tmp_path, (None, [f"1. {_L}"], 0.0))
    assert r.traslape_max_numero.valor == "6" and r.avisos == []


def test_a_scoping_heading_anywhere_above_the_boundary_makes_the_block_ambiguous(tmp_path):
    for arriba in (
        [("COLUMNAS :", [], 0.0), ("REFUERZO :", [], 0.0)],
        [("COLUMNAS :", [], 0.0), ("REFUERZO :", ["1. CONCRETO F'C=250"], 0.0)],
        [("COLUMNAS :", ["1. CONCRETO F'C=250", "2. LAS COTAS RIGEN"], 0.0), ("NOTAS :", [], 0.44)],
    ):
        r = _con_bloques(tmp_path, *arriba, (None, [f"1. {_L}"], _UN_HUECO_COMO_UNA_FIGURA))
        assert r.traslape_max_numero is None and r.avisos, arriba


def test_the_general_notes_heading_ends_what_is_looked_for_above_the_boundary(tmp_path):
    r = _con_bloques(
        tmp_path,
        ("NOTAS PARA ESCALERAS :", ["1. CONCRETO F'C=250"], 0.0),
        ("NOTAS GENERALES DE ESTRUCTURA.", [], 0.44),
        (None, [f"1. {_L}"], _UN_HUECO_COMO_UNA_FIGURA),
    )
    assert r.traslape_max_numero.valor == "6" and r.avisos == []


def test_a_block_with_a_heading_of_its_own_still_sits_under_the_scoping_block_above(tmp_path):
    # R50 sustituye lo de R49 (C y D del revisor leían): un encabezado general de otro bloque no
    # cierra lo que acota el de arriba, y uno de cimentación sigue restringiendo
    r = _con_bloques(
        tmp_path,
        ("NOTAS PARA ESCALERAS :", ["1. CONCRETO F'C=250"], 0.0),
        ("NOTAS GENERALES :", [f"1. {_L}"], _UN_HUECO_COMO_UNA_FIGURA),
    )
    assert r.traslape_max_numero is None and r.avisos
    r = _con_bloques(
        tmp_path,
        ("NOTAS DE CIMENTACION", [], 0.0),
        ("COLUMNAS :", [f"1. {_RC}", f"2. {_PE}"], _UN_HUECO_COMO_UNA_FIGURA),
    )
    assert _nada_de_la_nota(r, _R) and r.primer_estribo_m == {} and r.avisos


def test_the_first_stirrup_default_never_crosses_a_boundary_even_for_generic_headings(tmp_path):
    r = _con_bloques(
        tmp_path, ("TRABES :", [], 0.0), (None, [f"1. {_PE}"], _UN_HUECO_COMO_UNA_FIGURA)
    )
    assert r.primer_estribo_m == {} and r.avisos


def test_the_unknown_subtitle_under_a_heading_still_belongs_to_it(tmp_path):
    # la excepción del renglón alto con un encabezado justo encima sigue valiendo
    r = _con_bloques(tmp_path, ("COLUMNAS :", [], 0.0), ("Detalles", [f"1. {_L}"], 0.0))
    assert r.traslape_max_numero is None and r.avisos


def test_a_note_keeps_every_heading_above_it_with_a_mark_where_its_block_ends(tmp_path):
    entidades = _entidades_de(
        tmp_path,
        _apilar(
            ("COLUMNAS :", [], 0.0),
            ("REFUERZO :", [], 0.0),
            (None, [f"1. {_L}"], _UN_HUECO_COMO_UNA_FIGURA),
            ("MATERIALES :", [f"1. {_L}", "2. LAS COTAS RIGEN"], 0.44),
        ),
    )
    notas, _ = leer_notas(_textos(entidades), lambda e: "ES-001")
    sin_encabezado, con_el_suyo = sorted(notas, key=lambda n: n.seccion)[:2]
    assert (sin_encabezado.seccion, sin_encabezado.encabezado) == ("", "")
    assert sin_encabezado.cadenas == [[LIMITE_DE_BLOQUE, "REFUERZO :", "COLUMNAS :"]]
    # el que tiene encabezado propio lo tiene en su bloque y los de arriba más allá de la marca
    assert con_el_suyo.seccion == "MATERIALES"
    assert con_el_suyo.cadenas[0][0] == "MATERIALES :"


# --- Task 5c, R50: el alcance sólo crece hacia abajo ---------------------------------------------
# Todo encabezado que acota y todo encabezado de cimentación de arriba, hasta «NOTAS GENERALES DE
# ESTRUCTURA», vale para una nota aunque haya un hueco, una numeración que empieza de nuevo, un
# título, un renglón suelto o un encabezado general en medio. Los límites sólo niegan los elementos
# que un primer estribo sin elementos tomaría del encabezado.

_ACERO_CON_SUBLISTA = [
    "1. EL ACERO SERA:",
    "1) FY=4200 KG/CM2 EN VARILLAS.",
    "2) FY=6000 KG/CM2 EN MALLAS.",
]
_ZAPATAS = "1. LAS ZAPATAS SE DESPLANTARAN A 1.20 M."
_CONCRETO = "1. EL CONCRETO SERA F'C=250 KG/CM2."
_TRASLAPE_3 = f"3. {_L}."
_CUBRE_TRABES = "EL RECUBRIMIENTO SERA DE 5 CM EN TRABES"
_CUBRE_COLUMNAS = "EL RECUBRIMIENTO SERA DE 4 CM EN COLUMNAS"
_FRAGMENTO = ("EN UNA MISMA SECCION.", 0.6)

# (nombre del caso del revisor, bloques, regla que no se debe leer)
_CASOS_DE_ALCANCE_QUE_CRECE = [
    pytest.param(
        [
            ("NOTAS DE CIMENTACION :", [_ZAPATAS], 0.0),
            (None, [f"2. {_CUBRE_TRABES}"], _UN_HUECO_COMO_UNA_FIGURA),
        ],
        _R,
        id="F1 cimentacion + hueco, recubrimiento de trabes",
    ),
    pytest.param(
        [
            ("NOTAS DE CIMENTACION :", [_ZAPATAS], 0.0),
            (None, ["2. EL RECUBRIMIENTO LIBRE EN TRABES Y COLUMNAS SERA DE 5 CM."], 1.4),
        ],
        _R,
        id="F1b cimentacion + hueco, trabes y columnas",
    ),
    pytest.param(
        [
            ("NOTAS DE CIMENTACION :", [_ZAPATAS, "2. EL CONCRETO SERA F'C=250 KG/CM2."], 0.0),
            (None, [f"1. {_CUBRE_TRABES}"], 0.0),
        ],
        _R,
        id="F6 cimentacion + la numeracion empieza de nuevo",
    ),
    pytest.param(
        [
            ("NOTAS DE CIMENTACION :", ["1. EL CONCRETO DE LAS ZAPATAS SERA F'C=250 KG/CM2."], 0.0),
            ("Recubrimientos", [f"2. {_CUBRE_TRABES}"], 0.0),
        ],
        _R,
        id="F7 cimentacion + un titulo que no se reconoce",
    ),
    pytest.param(
        [
            ("NOTAS DE CIMENTACION :", [_ZAPATAS], 0.0),
            ("REFUERZO :", [f"1. {_CUBRE_TRABES}"], _UN_HUECO_COMO_UNA_FIGURA),
        ],
        _R,
        id="F8 cimentacion + hueco + un encabezado general",
    ),
    pytest.param(
        [
            ("NOTAS DE CIMENTACION :", [_ZAPATAS], 0.0),
            (
                None,
                ["2. EL PRIMER ESTRIBO SE COLOCARA A 5 CM EN TRABES"],
                _UN_HUECO_COMO_UNA_FIGURA,
            ),
        ],
        _P,
        id="F9 cimentacion + hueco, primer estribo de trabes",
    ),
    pytest.param(
        [
            (
                "NOTAS DE CIMENTACION :",
                [
                    "1. EL CONCRETO DE LAS ZAPATAS SERA F'C=250 KG/CM2.",
                    *_ACERO_CON_SUBLISTA[:1],
                    *_ACERO_CON_SUBLISTA[1:],
                    f"3. {_CUBRE_COLUMNAS}",
                ],
                0.0,
            ),
        ],
        _R,
        id="F2 cimentacion + una sublista que empieza de nuevo",
    ),
    pytest.param(
        [("NOTAS PARA ESCALERAS :", [_CONCRETO, *_ACERO_CON_SUBLISTA, _TRASLAPE_3], 0.0)],
        _T,
        id="F2s escaleras + una sublista que empieza de nuevo",
    ),
    pytest.param(
        [
            ("NOTAS PARA ESCALERAS :", [_CONCRETO], 0.0),
            (
                None,
                ["2. NO SE TRASLAPARA MAS DEL 50% DEL ACERO", _FRAGMENTO, _TRASLAPE_3],
                _UN_HUECO_COMO_UNA_FIGURA,
            ),
        ],
        _T,
        id="F3 escaleras + hueco + un renglon suelto en mayusculas",
    ),
    pytest.param(
        [
            (
                "NOTAS PARA ESCALERAS :",
                [
                    *_ACERO_CON_SUBLISTA,
                    "2. NO SE TRASLAPARA MAS DEL 50% DEL ACERO",
                    _FRAGMENTO,
                    _TRASLAPE_3,
                ],
                0.0,
            )
        ],
        _T,
        id="F3b escaleras + una sublista + un renglon suelto en mayusculas",
    ),
    pytest.param(
        [
            (
                "COLUMNAS :",
                [
                    *_ACERO_CON_SUBLISTA,
                    "2. NO SE TRASLAPARA MAS DEL 50% DEL ACERO",
                    _FRAGMENTO,
                    "3. EL RECUBRIMIENTO LIBRE SERA DE 4 CM.",
                    f"4. {_L}.",
                ],
                0.0,
            )
        ],
        _T,
        id="F3c columnas + una sublista + un renglon suelto en mayusculas",
    ),
    pytest.param(
        [
            ("NOTAS PARA ESCALERAS :", [_CONCRETO], 0.0),
            (None, ["DETALLE TIPO.", f"2. {_L}."], _UN_HUECO_COMO_UNA_FIGURA),
        ],
        _T,
        id="F4 escaleras + hueco + un pie de figura en mayusculas",
    ),
    pytest.param(
        [
            ("NOTAS PARA ESCALERAS :", [_CONCRETO], 0.0),
            ("REFUERZO :", [f"1. {_L}."], _UN_HUECO_COMO_UNA_FIGURA),
        ],
        _T,
        id="F5 escaleras + hueco + un encabezado general",
    ),
]


@pytest.mark.parametrize(("bloques", "regla"), _CASOS_DE_ALCANCE_QUE_CRECE)
def test_a_scope_only_grows_downwards_whatever_comes_in_between(tmp_path, bloques, regla):
    r = _con_bloques(tmp_path, *bloques)
    assert _nada_de_la_nota(r, regla), getattr(r, regla)
    assert r.avisos


def test_the_controls_of_the_scope_cases_still_read_or_report_as_before(tmp_path):
    # F1c: la cimentación sin hueco ya era un aviso; sin un encabezado de arriba se lee
    r = _con_bloques(tmp_path, ("NOTAS DE CIMENTACION :", [_ZAPATAS, f"2. {_CUBRE_TRABES}"], 0.0))
    assert _nada_de_la_nota(r, _R) and r.avisos
    r = _con_bloques(tmp_path, (None, [_ZAPATAS, f"2. {_CUBRE_TRABES}"], 0.0))
    assert r.recubrimiento_m["trabe"].valor == 0.05 and r.avisos == []
    # un encabezado general solo, con hueco o con sublista, no cambia nada
    r = _con_bloques(tmp_path, ("REFUERZO :", [_CONCRETO, *_ACERO_CON_SUBLISTA, _TRASLAPE_3], 0.0))
    assert r.traslape_max_numero.valor == "6" and r.avisos == []


def test_the_foundation_restriction_survives_a_boundary_for_the_stirrup_default_too(tmp_path):
    r = _con_bloques(
        tmp_path,
        ("NOTAS DE CIMENTACION :", [_ZAPATAS], 0.0),
        ("TRABES :", [f"1. {_PE}"], _UN_HUECO_COMO_UNA_FIGURA),
    )
    assert r.primer_estribo_m == {} and r.avisos


# --- Task 5c, R50-4: una cláusula que no es corta no puede tardar --------------------------------


def test_a_long_clause_that_cannot_match_is_rejected_fast():
    import time

    from klave_engine.estructura.reglas import _CLAUSULA_CORTA

    for clausula in (
        " ".join(["ESCALERAS" * 6 + "XXXXXX"] * 6),
        " ".join(["A" * 60 + "!"] * 6),
        " ".join(["~" * 60] * 6 + ["A"]),
        " ".join(["A1-" * 20] * 5),
        ("A" * 5000) + " " + ("B" * 5000) + " C D E",
    ):
        t = time.perf_counter()
        _CLAUSULA_CORTA.fullmatch(clausula)
        assert time.perf_counter() - t < 0.1, clausula[:40]


def test_a_pathological_note_is_read_fast(tmp_path):
    import time

    larga = " ".join(["ESCALERAS" * 6 + "XXXXXX"] * 6)
    t = time.perf_counter()
    r = _con_notas(tmp_path, [f"4. {_L}. {larga}."])
    assert time.perf_counter() - t < 2.0
    assert r.traslape_max_numero.valor == "6"


def test_a_rule_for_a_family_inside_the_scope_is_read_after_a_gap(tmp_path):
    # el alcance es el de los elementos del encabezado: «COLUMNAS :» deja leer lo de columnas
    r = _con_bloques(
        tmp_path,
        ("COLUMNAS :", [], 0.0),
        (None, [f"1. {_RC}"], _UN_HUECO_COMO_UNA_FIGURA),
    )
    assert r.recubrimiento_m["columna"].valor == 0.04 and r.avisos == []
    # … pero ni lo de otro elemento ni una regla de todo el proyecto
    r = _con_bloques(
        tmp_path,
        ("COLUMNAS :", [], 0.0),
        (None, ["1. EL RECUBRIMIENTO SERA DE 4 CM EN TRABES"], _UN_HUECO_COMO_UNA_FIGURA),
    )
    assert _nada_de_la_nota(r, _R) and r.avisos


def test_two_frames_sharing_a_code_are_said_not_merged_in_silence(tmp_path):
    # R80: las reglas nombran cada hoja por su código; dos marcos con el mismo no se separan y
    # se dice (como en las definiciones).
    from klave_engine.detection.frames import SheetFrame

    entidades = _dibujo(
        tmp_path,
        bloques=[
            ([("REFUERZO :", MARINA_REFUERZO)], 1),
            ([("REFUERZO :", MARINA_PB_REFUERZO)], 1),
        ],
    )
    marcos = [
        SheetFrame(frame_id="a", bbox=(40, 10, 140, 60), source_file="marina.dxf", code="ES-000"),
        SheetFrame(frame_id="b", bbox=(40, -60, 140, -10), source_file="marina.dxf", code="ES-000"),
    ]
    r = leer_reglas(entidades, frames=marcos)
    (aviso,) = [a for a in r.avisos if "marcos distintos" in a]
    assert "a de marina.dxf" in aviso and "b de marina.dxf" in aviso
    assert r.para("ES-000").traslape_max_numero.en_conflicto is True
    sin_choque = leer_reglas(
        entidades, frames=[marcos[0], marcos[1].model_copy(update={"code": "ES-100"})]
    )
    assert not [a for a in sin_choque.avisos if "marcos distintos" in a]


# --- el fy de las varillas y lo leído (tarea 8b, ronda 2: R119) -------------------------------

_FY_MARINA = (
    "2.\\t ACERO DE REFUERZO CON F'Y=4200KG/CM2 EN VARILLAS DEL No.3\\PEN ADELANTE Y "
    "F'Y=2530KG/CM2 EN VARILLAS DEL No.2."
)
# ES-000 y otras hojas de Marina: el MTEXT parte «KG/CM2» en dos renglones.
_FY_MARINA_PARTIDA = (
    "2.\\t ACERO DE REFUERZO CON F'Y=4200KG/CM2 EN VARILLAS DEL No.3\\PEN ADELANTE Y "
    "F'Y=2530K\\PG/CM2 EN VARILLAS DEL No.2."
)


def _fy(r):
    return {n: d.valor for n, d in r.fy_kg_cm2.items()}


@pytest.mark.parametrize("mtext", [_FY_MARINA, _FY_MARINA_PARTIDA])
def test_the_fy_of_each_bar_is_read_from_the_materials_note(tmp_path, mtext):
    # R119: «DEL No.3 EN ADELANTE» va a todas las varillas desde el #3; el #2 tiene el suyo.
    r = leer_reglas(_dibujo(tmp_path, tabla=False, mtexts=[(mtext, 5.0, 5.0)]), frames=[])
    esperado = {n: 4200 for n in NUMEROS if float(n) >= 3} | {"2": 2530}
    assert _fy(r) == esperado and r.avisos == []
    assert r.fy_kg_cm2["3"].fuente == "nota" and "F'Y=4200" in r.fy_kg_cm2["3"].texto
    # Lo leído son los renglones de la nota 2 del MTEXT, no el MTEXT entero.
    ((_, renglones),) = r.textos_leidos.items()
    assert renglones[0].startswith("2.") and "No.2." in renglones[-1]


@pytest.mark.parametrize(
    "mtext",
    [
        # una cláusula de más: no es la nota conocida entera
        "2. ACERO DE REFUERZO CON F'Y=4200KG/CM2 EN VARILLAS DEL No.3 EN ADELANTE, SALVO EN "
        "ESTRIBOS",
        # una negación
        "2. ACERO DE REFUERZO CON F'Y=4200KG/CM2 EN VARILLAS DEL No.3 EN ADELANTE, NO EN LOSAS",
    ],
)
def test_an_fy_note_that_is_not_read_whole_is_an_aviso(tmp_path, mtext):
    r = leer_reglas(_dibujo(tmp_path, tabla=False, mtexts=[(mtext, 5.0, 5.0)]), frames=[])
    assert r.fy_kg_cm2 == {} and r.textos_leidos == {}
    assert any("dice el fy de las varillas, pero no se pudo leer entera" in a for a in r.avisos)


def test_an_fy_for_all_bars_is_every_bars(tmp_path):
    # «1) FY=4200 KG/CM2 EN VARILLAS.»: sin número, todas las varillas.
    r = _con_notas(tmp_path, ["1. EL ACERO SERA:", "1) FY=4200 KG/CM2 EN VARILLAS."], "NOTAS :")
    assert _fy(r) == dict.fromkeys(NUMEROS, 4200)


def test_the_rows_of_a_note_read_as_a_rule_are_consumed_in_every_copy(tmp_path):
    # R119: la nota de traslapes y soldadura se leyó: sus renglones, de las dos copias, son de
    # las reglas (nadie más los tiene que leer).
    r = leer_reglas(
        _dibujo(tmp_path, tabla=False, bloques=[([("REFUERZO :", MARINA_REFUERZO)], 2)]),
        frames=[],
    )
    assert r.soldar_desde_numero.valor == "8"
    assert len(r.textos_leidos) >= 2 * 4 and all(v == [] for v in r.textos_leidos.values())
