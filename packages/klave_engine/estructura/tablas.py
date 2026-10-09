"""Las tablas del plano: textos sueltos que el dibujante alineó en columnas y renglones.

Un plano no dice «esto es una tabla»: son textos. Esta lectura la reconstruye desde lo único
que el dibujante sí puso, el renglón de encabezados. Los encabezados fijan las columnas; la
columna ancla (la primera, la que nombra el renglón) fija los renglones; cada texto que cae
debajo entra en la celda donde se cruzan su columna y su renglón. Lo que no cae en ninguna
celda (una nota, una unidad, el título) se queda fuera: nunca se inventa una celda, y un
texto con cifras dentro de la tabla que no se pudo colocar se anota en ``sin_celda`` en vez
de perderse.

Las posiciones son siempre las de ``ancla_texto``: el punto donde el dibujante puso el texto."""

import math
import re
import statistics
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from klave_engine.dxf.entities import NormalizedEntity
from klave_engine.estructura.asociacion import ancla_texto
from klave_engine.geometry.bbox import BBox, bbox_union_all

# Un renglón de encabezados (o de celdas) está en una línea si sus textos difieren a lo más
# esto (× el alto del texto).
_TOLERANCIA_LINEA = 0.5
# Una columna ancla sigue mientras el hueco entre renglones no pase de esto (× el alto).
_HUECO_MAXIMO = 2.5
# Después de un corte, un renglón que aparece a esto (× el hueco máximo) todavía se considera
# parte de la tabla —un renglón en blanco en medio—: no se lee, pero se avisa.
_ALCANCE_DEL_HUECO = 3
_CIFRA = re.compile(r"\d")
# Lo que parece un número de varilla o de fila escrito de otra manera: «9», «2.50», «#9», «3/8».
_CASI_NUMERO = re.compile(r"[#\s]*\d[\d.,/\s]*")


def parece_numero(texto: str) -> bool:
    """Si el texto parece un número escrito de otra manera: «9», «2.50», «#9», «3/8»."""
    return _CASI_NUMERO.fullmatch(texto) is not None


Motivo = Literal["fuera_de_columna", "fuera_de_renglon", "tras_un_hueco", "fila_descartada"]


class TextoSinCelda(BaseModel):
    """Un texto con cifras que está dentro de la tabla y no entró en ninguna celda.

    ``renglon`` es el texto de la fila de la tabla más cercana, ``columna`` el encabezado más
    cercano (si el texto está en una columna). ``motivo``: ``fuera_de_columna`` (entre dos
    columnas), ``fuera_de_renglon`` (no está sobre la línea de ninguna fila), ``tras_un_hueco``
    (la tabla sigue después de un hueco) o ``fila_descartada`` (la fila no es de las que se
    piden)."""

    entidad: str
    texto: str
    motivo: Motivo
    renglon: str | None = None
    columna: str | None = None


class Tabla(BaseModel):
    """Una tabla leída: ``filas`` trae sólo las celdas con texto (las vacías no aparecen).

    ``sin_celda`` son los textos con cifras de la tabla que no se usaron; ``avisos`` dicen por
    qué un renglón de encabezados no se pudo leer (entonces ``filas`` va vacía)."""

    encabezados: list[str]
    filas: list[dict[str, str]]
    entidades: list[str]
    hoja: str
    bbox: BBox
    sin_celda: list[TextoSinCelda] = []
    avisos: list[str] = []


@dataclass(frozen=True)
class _Texto:
    """Un texto del plano ya con su posición (la de ``ancla_texto``) y su alto."""

    entidad: NormalizedEntity
    texto: str
    x: float
    y: float
    alto: float

    @property
    def id(self) -> str:
        return self.entidad.entity_id


def _limpio(texto: str) -> str:
    return " ".join(texto.split())


def _clave(texto: str) -> str:
    """Para comparar encabezados: sin mayúsculas, sin acentos y sin espacios de más."""
    descompuesto = unicodedata.normalize("NFKD", _limpio(texto))
    return "".join(c for c in descompuesto if not unicodedata.combining(c)).casefold()


def _alto(e: NormalizedEntity) -> float:
    """El alto del texto: el de la letra, o el de su caja si el dibujo no lo trae."""
    alto = e.properties.get("height")
    if not isinstance(alto, int | float) or alto <= 0:
        alto = e.bbox[3] - e.bbox[1]
    return float(alto) if alto > 0 else 1e-6


def _mediana(valores: list[float]) -> float:
    return float(statistics.median(valores))


def leer_tablas(
    textos: list[NormalizedEntity],
    encabezados: tuple[str, ...],
    ancla: str,
    hoja_de: Callable[[NormalizedEntity], str],
    *,
    fila_valida: Callable[[str], bool] | None = None,
    hueco_maximo: float = _HUECO_MAXIMO,
) -> list[Tabla]:
    """Las tablas cuyo renglón de encabezados trae todos los ``encabezados``.

    Encabezado: cada ficha del renglón es un texto igual a la ficha pedida (sin distinguir
    mayúsculas, acentos ni espacios de más), todos en una línea (a lo más media altura de
    diferencia), en la misma hoja y de izquierda a derecha en el orden de ``encabezados``:
    cada ficha es la más cercana a la derecha de la anterior (a la izquierda del ancla, la
    más cercana a su izquierda) y sin pasar del ancla de la tabla vecina en la misma línea, así
    que con varias copias cada tabla toma las suyas y una copia dañada no se lleva las de otra.
    Si el renglón empezó (al menos la mitad de las fichas) y no se puede completar en orden, o
    una ficha aparece dos veces entre sus vecinas, la tabla no se lee: se devuelve sin filas y
    con su aviso en ``Tabla.avisos``.

    La columna ancla son los textos bajo ``ancla`` (a lo más media separación entre
    encabezados, y más cerca de ella que de otro encabezado), hacia abajo mientras el hueco
    entre dos no pase de ``hueco_maximo`` veces el alto del texto; cada uno es un renglón.
    Una celda es un texto de una línea (o varios en la misma línea, unidos de izquierda a
    derecha); las celdas de varias líneas todavía no se leen. Cada otro texto debajo del
    encabezado entra en la celda del encabezado más cercano por ``x`` (a lo más media
    separación entre encabezados) y del renglón más cercano por ``y`` si está sobre su línea.

    Lo que no entra en ninguna celda no se descarta en silencio: un texto con cifras dentro
    de la tabla (bajo el encabezado, hasta media separación después de la última fila) que
    cae entre columnas, fuera de la línea de toda fila o después de un hueco se anota en
    ``Tabla.sin_celda``, igual que una fila descartada que parece un número.

    ``fila_valida`` dice qué textos de la columna ancla son renglón de verdad. Un texto que
    no lo es (un «No.», una unidad) sigue ocupando su lugar —lo que cae junto a él es suyo y
    se descarta con él— pero no es fila ni deja sus celdas a la fila de al lado. Sin él, todo
    texto de la columna ancla es renglón. Una tabla sin renglones ni nada que avisar no se
    devuelve."""
    if ancla not in encabezados:
        raise ValueError(f"el ancla {ancla!r} no es uno de los encabezados {encabezados!r}")

    hojas: dict[str, str] = {}

    def hoja(e: NormalizedEntity) -> str:
        if e.entity_id not in hojas:
            hojas[e.entity_id] = hoja_de(e)
        return hojas[e.entity_id]

    todos: list[_Texto] = []
    for e in textos:
        if not e.is_textual or not e.text:
            continue
        limpio = _limpio(e.text)
        if not limpio:
            continue
        x, y = ancla_texto(e)
        todos.append(_Texto(e, limpio, x, y, _alto(e)))

    claves = {_clave(h) for h in encabezados}
    candidatos: dict[str, list[_Texto]] = {}
    for t in todos:
        if _clave(t.texto) in claves:
            candidatos.setdefault(_clave(t.texto), []).append(t)

    usados: set[str] = set()
    tablas: list[Tabla] = []
    for a in _en_orden_de_lectura(candidatos.get(_clave(ancla), []), hoja):
        if a.id in usados:
            continue
        cabecera, avisos = _cabecera(a, encabezados, ancla, candidatos, usados, hoja)
        if avisos:
            tablas.append(
                Tabla(
                    encabezados=list(encabezados),
                    filas=[],
                    entidades=[t.id for t in cabecera.values()],
                    hoja=hoja(a.entidad),
                    bbox=bbox_union_all(t.entidad.bbox for t in cabecera.values()),
                    avisos=avisos,
                )
            )
            continue
        if len(cabecera) < len(encabezados):
            continue  # un «VARILLA» suelto en el plano, no un renglón de encabezados
        tabla = _leer_una(
            cabecera, a, encabezados, ancla, todos, hoja, usados, fila_valida, hueco_maximo
        )
        if tabla is not None:
            tablas.append(tabla)
            usados.update(tabla.entidades)
            usados.update(s.entidad for s in tabla.sin_celda)
    return tablas


def _en_orden_de_lectura(
    anclas: list[_Texto], hoja: Callable[[NormalizedEntity], str]
) -> list[_Texto]:
    """Por hoja, de arriba abajo y de izquierda a derecha; la misma línea con tolerancia, para
    que un ruido de 1e-9 en ``y`` no cambie el orden de dos tablas lado a lado."""
    orden: list[_Texto] = []
    for nombre in sorted({hoja(t.entidad) for t in anclas}):
        de_la_hoja = sorted((t for t in anclas if hoja(t.entidad) == nombre), key=lambda t: -t.y)
        linea: list[_Texto] = []
        for t in de_la_hoja:
            if linea and abs(t.y - linea[0].y) > _TOLERANCIA_LINEA * linea[0].alto:
                orden += sorted(linea, key=lambda u: u.x)
                linea = []
            linea.append(t)
        orden += sorted(linea, key=lambda u: u.x)
    return orden


def _cabecera(
    a: _Texto,
    encabezados: tuple[str, ...],
    ancla: str,
    candidatos: dict[str, list[_Texto]],
    usados: set[str],
    hoja: Callable[[NormalizedEntity], str],
) -> tuple[dict[str, _Texto], list[str]]:
    """El renglón de encabezados que parte de ``a``, en orden de izquierda a derecha.

    Devuelve las fichas elegidas y los avisos. Sin avisos y con todas las fichas, el renglón
    está completo; sin avisos y con fichas de menos no hubo renglón (``a`` está suelto)."""
    hoja_a = hoja(a.entidad)
    tolerancia = _TOLERANCIA_LINEA * a.alto

    def en_mi_linea(t: _Texto) -> bool:
        return abs(t.y - a.y) <= tolerancia and hoja(t.entidad) == hoja_a

    # El renglón de otra tabla (una copia al lado) empieza en su propio ancla: las fichas de
    # esta tabla caen entre el ancla de su izquierda y el de su derecha, no más allá.
    otras = [t.x for t in candidatos.get(_clave(ancla), []) if t.id != a.id and en_mi_linea(t)]
    izquierda = max((x for x in otras if x < a.x), default=-math.inf)
    derecha = min((x for x in otras if x > a.x), default=math.inf)
    en_linea: dict[str, list[_Texto]] = {
        h: [
            t
            for t in candidatos.get(_clave(h), [])
            if t.id not in usados and t.id != a.id and en_mi_linea(t) and izquierda < t.x < derecha
        ]
        for h in encabezados
        if h != ancla
    }
    cabecera: dict[str, _Texto] = {ancla: a}
    avisos: list[str] = []
    i = encabezados.index(ancla)
    # A la derecha del ancla cada ficha es la más cercana a la derecha de la anterior; a la
    # izquierda, la más cercana a su izquierda.
    for nombres, signo in ((encabezados[i + 1 :], 1), (tuple(reversed(encabezados[:i])), -1)):
        previo = a
        for h in nombres:
            posibles = sorted(
                (t for t in en_linea[h] if signo * (t.x - previo.x) > 0), key=lambda t: signo * t.x
            )
            if not posibles:
                lado = "a la derecha" if signo > 0 else "a la izquierda"
                avisos.append(
                    f"el renglón de encabezados que empieza en «{ancla}» no se puede leer: "
                    f"no hay «{h}» {lado} de «{_nombre_de(cabecera, previo)}» en su línea"
                )
                break
            cabecera[h] = previo = posibles[0]
        if avisos:
            break
    if avisos:
        # Sólo se avisa si el dibujante llegó a escribir al menos la mitad del renglón.
        presentes = sum(1 for h, ts in en_linea.items() if ts)
        if 2 * presentes < len(en_linea):
            return {}, []
        return cabecera, avisos

    # Una ficha que aparece otra vez entre sus vecinas no se puede distinguir: no se adivina.
    nombres_en_orden = list(encabezados)
    for k, h in enumerate(nombres_en_orden):
        if h == ancla or k == 0 or k == len(nombres_en_orden) - 1:
            continue
        izquierda = cabecera[nombres_en_orden[k - 1]].x
        derecha = cabecera[nombres_en_orden[k + 1]].x
        if any(
            t.id != cabecera[h].id and min(izquierda, derecha) < t.x < max(izquierda, derecha)
            for t in en_linea[h]
        ):
            avisos.append(
                f"el renglón de encabezados que empieza en «{ancla}» es ambiguo: «{h}» aparece "
                f"dos veces entre «{nombres_en_orden[k - 1]}» y «{nombres_en_orden[k + 1]}»"
            )
    return cabecera, avisos


def _nombre_de(cabecera: dict[str, _Texto], texto: _Texto) -> str:
    return next(h for h, t in cabecera.items() if t is texto)


def _leer_una(
    cabecera: dict[str, _Texto],
    a: _Texto,
    encabezados: tuple[str, ...],
    ancla: str,
    todos: list[_Texto],
    hoja: Callable[[NormalizedEntity], str],
    usados: set[str],
    fila_valida: Callable[[str], bool] | None,
    hueco_maximo: float,
) -> Tabla | None:
    fichas = list(cabecera.values())
    alto = _mediana([t.alto for t in fichas])
    y_cabecera = _mediana([t.y for t in fichas])
    xs = sorted(t.x for t in fichas)
    separaciones = [b - a_ for a_, b in zip(xs, xs[1:], strict=False)]
    tolerancia_x = (_mediana(separaciones) if separaciones else 6 * alto) / 2
    linea = _TOLERANCIA_LINEA * alto
    cabecera_ids = {t.id for t in fichas}
    hoja_a = hoja(a.entidad)

    def columna(t: _Texto) -> str | None:
        """El encabezado más cercano por ``x``, si está a lo más a media separación."""
        nombre, ficha = min(cabecera.items(), key=lambda kv: abs(kv[1].x - t.x))
        return nombre if abs(ficha.x - t.x) <= tolerancia_x else None

    # Todo lo que cuelga de este renglón de encabezados: bajo él y dentro de lo ancho de la
    # tabla, en su hoja y sin usar.
    debajo = [
        t
        for t in todos
        if t.id not in usados
        and t.id not in cabecera_ids
        and t.y < y_cabecera - linea
        and xs[0] - tolerancia_x <= t.x <= xs[-1] + tolerancia_x
    ]
    debajo = [t for t in debajo if hoja(t.entidad) == hoja_a]

    # La columna ancla: hacia abajo mientras los huecos no pasen de ``hueco_maximo`` veces el alto.
    renglones: list[_Texto] = []
    resto: list[_Texto] = []  # lo que sigue en la columna ancla después de un hueco
    previo = y_cabecera
    en_ancla = sorted((t for t in debajo if columna(t) == ancla), key=lambda t: (-t.y, t.x))
    for k, t in enumerate(en_ancla):
        if previo - t.y > hueco_maximo * alto:
            resto = en_ancla[k:]
            break
        if renglones and renglones[-1].y - t.y <= linea:
            continue  # el mismo renglón escrito dos veces: vale el primero
        if _clave(t.texto) == _clave(ancla):
            break  # el encabezado de otra copia debajo
        renglones.append(t)
        previo = t.y

    # Después de un hueco la tabla puede seguir (un renglón en blanco en medio): no se lee,
    # pero lo que sigue, a no mucha distancia, se anota.
    tras_hueco: list[_Texto] = []
    ultimo = previo
    for t in resto:
        limite = hueco_maximo * alto * (1 if tras_hueco else _ALCANCE_DEL_HUECO)
        if ultimo - t.y > limite or _clave(t.texto) == _clave(ancla):
            break
        if fila_valida is None or fila_valida(t.texto) or parece_numero(t.texto):
            tras_hueco.append(t)  # lo demás (una nota, una unidad) no es un renglón que falte
            ultimo = t.y
    if not renglones and not tras_hueco:
        return None

    pasos = [a_.y - b.y for a_, b in zip(renglones, renglones[1:], strict=False)]
    tolerancia_y = (_mediana(pasos) if pasos else 2 * alto) / 2
    validos = [r for r in renglones if fila_valida is None or fila_valida(r.texto)]
    ultima_fila = tras_hueco[-1] if tras_hueco else (validos or renglones or [a])[-1]
    y_fin = ultima_fila.y - tolerancia_y  # más abajo ya no es de la tabla
    fin_de_la_cadena = renglones[-1].y if renglones else y_cabecera

    celdas: list[dict[str, list[_Texto]]] = [{} for _ in renglones]
    propios = {r.id for r in renglones}
    marcas_del_hueco = {t.id for t in tras_hueco}
    sin: list[tuple[_Texto, TextoSinCelda]] = []

    def anotar(t: _Texto, motivo: Motivo, nombre: str | None) -> None:
        if not _CIFRA.search(t.texto):
            return
        cerca = min(renglones, key=lambda r: abs(r.y - t.y)).texto if renglones else None
        anotado = TextoSinCelda(
            entidad=t.id, texto=t.texto, motivo=motivo, renglon=cerca, columna=nombre
        )
        sin.append((t, anotado))

    for t in debajo:
        if t.id in propios or t.y < y_fin:
            continue
        nombre = columna(t)
        if t.id in marcas_del_hueco or t.y < fin_de_la_cadena - tolerancia_y:
            anotar(t, "tras_un_hueco", nombre)
        elif nombre is None:
            anotar(t, "fuera_de_columna", None)
        elif nombre == ancla:
            anotar(t, "fuera_de_renglon", nombre)  # un renglón repetido en la misma línea
        else:
            i = min(range(len(renglones)), key=lambda k: abs(renglones[k].y - t.y))
            if abs(renglones[i].y - t.y) <= linea:
                celdas[i].setdefault(nombre, []).append(t)
            else:
                anotar(t, "fuera_de_renglon", nombre)

    filas: list[dict[str, str]] = []
    usadas: list[_Texto] = list(fichas)
    for renglon, contenido in zip(renglones, celdas, strict=True):
        if fila_valida is not None and not fila_valida(renglon.texto):
            if parece_numero(renglon.texto):
                descartada = TextoSinCelda(
                    entidad=renglon.id,
                    texto=renglon.texto,
                    motivo="fila_descartada",
                    renglon=renglon.texto,
                    columna=ancla,
                )
                sin.append((renglon, descartada))
            continue
        fila = {ancla: renglon.texto}
        usadas.append(renglon)
        for nombre in encabezados:
            if nombre in contenido:
                celda = sorted(contenido[nombre], key=lambda t: (t.x, -t.y))
                fila[nombre] = " ".join(t.texto for t in celda)
                usadas.extend(celda)
        filas.append(fila)
    if not filas and not sin:
        return None
    sin.sort(key=lambda par: (-par[0].y, par[0].x))
    return Tabla(
        encabezados=list(encabezados),
        filas=filas,
        entidades=[t.id for t in usadas],
        hoja=hoja_a,
        bbox=bbox_union_all(t.entidad.bbox for t in usadas),
        sin_celda=[s for _, s in sin],
    )
