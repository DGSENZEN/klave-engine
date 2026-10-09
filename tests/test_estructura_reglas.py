"""Las tablas del plano, la tabla de varillas, las notas numeradas y las reglas del proyecto: lo
que el plano dice, copia por copia."""

import ezdxf
import pytest
from ezdxf.enums import TextEntityAlignment
from klave_engine.dxf.parser import DxfParser
from klave_engine.estructura.armado import NUMEROS
from klave_engine.estructura.asociacion import ancla_texto
from klave_engine.estructura.notas import leer_notas
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
    r = _con_notas(
        tmp_path,
        ["4. SE PERMITE TRASLAPAR VARILLA HASTA EL #6. LAS DE MAS DE LA No. 8 SE SOLDARAN"],
    )
    assert r.traslape_max_numero.valor == "6" and r.soldar_desde_numero is None
    (aviso,) = r.avisos
    assert "hasta qué varilla se traslapa" in aviso and "desde qué varilla se suelda" in aviso
    assert "mitad" in aviso


def test_the_other_half_missing_is_reported_too(tmp_path):
    r = _con_notas(
        tmp_path,
        ["4. NO SE TRASLAPARA VARILLA MAYOR AL #6 Y DEL #8 Y DIAMETROS MAYORES SE SOLDARAN"],
    )
    assert r.soldar_desde_numero.valor == "8" and r.traslape_max_numero is None
    (aviso,) = r.avisos
    assert "desde qué varilla se suelda" in aviso and "hasta qué varilla se traslapa" in aviso
    assert "mitad" in aviso


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


def test_a_materials_text_that_mentions_bars_from_a_number_on_stays_silent(tmp_path):
    mtext = (
        "2.\\t ACERO DE REFUERZO CON F'Y=4200KG/CM2 EN VARILLAS DEL No.3\\PEN ADELANTE Y "
        "F'Y=2530KG/CM2 EN VARILLAS DEL No.2."
    )
    r = leer_reglas(_dibujo(tmp_path, tabla=False, mtexts=[(mtext, 5.0, 5.0)]), frames=[])
    assert r.avisos == []


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
        "5. EL RECUBRIMIENTO DE LAS COLUMNAS DE ORILLA SERA 5.0 CM EN COLUMNAS",
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
