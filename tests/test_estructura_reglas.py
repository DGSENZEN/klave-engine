"""Las tablas del plano y la tabla de varillas: lo que el plano dice, copia por copia."""

import ezdxf
import pytest
from ezdxf.enums import TextEntityAlignment
from klave_engine.dxf.parser import DxfParser
from klave_engine.estructura.armado import NUMEROS
from klave_engine.estructura.asociacion import ancla_texto
from klave_engine.estructura.reglas import (
    ENCABEZADOS_VARILLA,
    TABLA_ESTANDAR,
    FilaVarilla,
    leer_tablas_de_varillas,
    numero_de_varilla,
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


def _poner(destino, texto, x, y, alinear=True):
    t = destino.add_text(texto, height=ALTO)
    if alinear:  # como Marina: todo el texto centrado, con punto de alineación
        t.set_placement((x, y), align=TextEntityAlignment.MIDDLE_CENTER)
    else:
        t.set_placement((x, y))


def _bloque(doc, nombre, cambio=None, sin=(), alinear=True):
    """El bloque de la tabla de Marina: título, encabezado, ``No.``, ``(cm)`` y ocho filas."""
    cambio = cambio or {}
    bloque = doc.blocks.new(nombre)
    _poner(bloque, "TABLA No.1", -1.5, 0.55, alinear)
    _poner(bloque, "TABLA DE VARILLAS", 0.0, 0.35, alinear)
    for encabezado, x in X_ENCABEZADO.items():
        _poner(bloque, encabezado, x, 0.0, alinear)
    _poner(bloque, "No.", X_ENCABEZADO["VARILLA"], -PASO, alinear)
    _poner(bloque, "(cm)", 1.6, -PASO, alinear)
    fila = 0
    for numero, valores in MARINA.items():
        if numero in sin:
            continue
        fila += 1
        y = -PASO - PASO * fila
        _poner(bloque, numero, X_ENCABEZADO["VARILLA"], y, alinear)
        for campo, valor in zip(CAMPOS, valores, strict=True):
            valor = cambio.get((numero, campo), valor)
            if valor is not None:
                _poner(bloque, str(valor), X_ENCABEZADO[campo], y, alinear)
    return bloque


def _entidades(
    tmp_path,
    copias=1,
    cambio=None,
    sin=(),
    desplazamiento=(40.0, 0.0),
    alinear=True,
):
    """Las copias van como inserciones del bloque ``NOTAS``; la última lleva ``cambio``/``sin``."""
    doc = ezdxf.new("R2010")
    _bloque(doc, "NOTAS", alinear=alinear)
    if cambio or sin:
        _bloque(doc, "NOTAS_ULTIMA", cambio, sin, alinear)
    msp = doc.modelspace()
    for i in range(copias):
        ultima = i == copias - 1 and (cambio or sin)
        msp.add_blockref(
            "NOTAS_ULTIMA" if ultima else "NOTAS",
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
    dato, contradicciones = tabla_de_varillas(_tablas(tmp_path, copias=2, lector=lector))
    t = dato.valor
    assert dato.fuente == "cuadro" and dato.copias == 2 and contradicciones == []
    assert sorted(t, key=float) == ["2.5", "3", "4", "5", "6", "8", "10", "12"]
    assert t["8"].model_dump() == dict(
        LA1=85, LA2=115, LT1=115, LT2=150, LG1=55, LG2=30, LG3=10, r=11
    )
    assert t["10"].LT1 is None and t["12"].LA2 == 255


@pytest.mark.parametrize("lector", ["varillas", "general"])
def test_copies_that_differ_are_reported(tmp_path, lector):
    dato, contradicciones = tabla_de_varillas(
        _tablas(tmp_path, copias=2, lector=lector, cambio={("8", "LT1"): 120})
    )
    assert contradicciones and "#8" in contradicciones[0] and "LT1" in contradicciones[0]


def test_no_table_means_standard_supuesto():
    dato, _ = tabla_de_varillas([])
    assert dato.fuente == "supuesto" and dato.valor["8"].LT1 is None


@pytest.mark.parametrize("alinear", [True, False])
@pytest.mark.parametrize("lector", ["varillas", "general"])
def test_every_value_of_the_drawing_is_read(tmp_path, alinear, lector):
    dato, contradicciones = tabla_de_varillas(_tablas(tmp_path, alinear=alinear, lector=lector))
    assert contradicciones == [] and dato.copias == 1 and dato.en_conflicto is False
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
    dato, contradicciones = tabla_de_varillas(general)
    assert contradicciones == [] and "No." not in dato.valor
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
            dato, contradicciones = tabla_de_varillas(leidas)
            assert dato.copias == 3 and contradicciones == [] and len(dato.valor) == 8


def test_each_table_keeps_its_hoja_entities_and_box(tmp_path):
    tablas = _tablas(tmp_path, copias=2, hoja_de=_por_columna)
    assert sorted(t.hoja for t in tablas) == ["ES-100", "ES-200"]
    t = next(t for t in tablas if t.hoja == "ES-200")
    assert t.encabezados == list(ENCABEZADOS_VARILLA)
    assert t.bbox[0] > 30 and t.bbox[2] < 50 and t.bbox[1] < -2 and t.bbox[3] > 0
    assert len(t.entidades) == 9 + 8 * 9 - 4  # encabezado + ocho filas, sin las cuatro celdas LT
    dato, _ = tabla_de_varillas(tablas)
    assert dato.copias == 2 and dato.hoja in ("ES-100", "ES-200")


def test_differing_copies_keep_both_readings(tmp_path):
    tablas = _tablas(tmp_path, copias=2, hoja_de=_por_columna, cambio={("8", "LT1"): 120})
    dato, contradicciones = tabla_de_varillas(tablas)
    assert dato.en_conflicto and dato.copias == 1 and len(dato.alternativas) == 1
    assert len(contradicciones) == 1
    frase = contradicciones[0]
    assert "#8" in frase and "LT1" in frase and "115" in frase and "120" in frase
    assert "ES-100" in frase and "ES-200" in frase  # dice en qué hoja está cada lectura


def test_the_odd_copy_loses_to_the_other_two(tmp_path):
    dato, contradicciones = tabla_de_varillas(
        _tablas(tmp_path, copias=3, cambio={("5", "r"): 8, ("8", "LT1"): 120})
    )
    assert dato.valor["5"].r == 7 and dato.valor["8"].LT1 == 115
    assert dato.copias == 2 and dato.en_conflicto
    assert len(contradicciones) == 2
    assert "#5 r" in contradicciones[0] and "#8 LT1" in contradicciones[1]


def test_a_bar_missing_in_a_copy_is_reported(tmp_path):
    dato, contradicciones = tabla_de_varillas(_tablas(tmp_path, copias=2, sin=("4",)))
    assert len(contradicciones) == 1
    assert "#4" in contradicciones[0] and "falta" in contradicciones[0]


def test_an_unreadable_cell_is_empty_and_reported_never_guessed(tmp_path):
    dato, contradicciones = tabla_de_varillas(_tablas(tmp_path, cambio={("8", "LT1"): "1l5"}))
    assert dato.valor["8"].LT1 is None and dato.valor["8"].LT2 == 150
    assert len(contradicciones) == 1
    assert (
        "#8" in contradicciones[0] and "LT1" in contradicciones[0] and "1l5" in contradicciones[0]
    )


def test_a_unit_after_the_number_is_still_the_number(tmp_path):
    dato, contradicciones = tabla_de_varillas(_tablas(tmp_path, cambio={("8", "LT1"): "115 cm"}))
    assert dato.valor["8"].LT1 == 115 and contradicciones == []


def test_tables_without_bar_rows_are_not_a_varillas_table(tmp_path):
    entidades = _textos(_entidades(tmp_path))
    solo_cabecera = [e for e in entidades if e.text in ENCABEZADOS_VARILLA or e.text == "No."]
    tablas = leer_tablas(solo_cabecera, ENCABEZADOS_VARILLA, "VARILLA", _hoja_del_archivo)
    dato, contradicciones = tabla_de_varillas(tablas)
    assert dato.fuente == "supuesto" and contradicciones == []


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
    dato, _ = tabla_de_varillas([])
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
        ("3/8", None),
        ("2.50", None),
    ],
)
def test_bar_numbers_are_the_ones_in_numeros(texto, esperado):
    assert numero_de_varilla(texto) == esperado


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

    assert _general(tmp_path, sin_un_token) == []
    assert _general(tmp_path, en_otra_linea) == []


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

    assert leer_tablas(textos, ("MARCA", "SECCION", "ARMADO"), "MARCA", por_x) == []
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
