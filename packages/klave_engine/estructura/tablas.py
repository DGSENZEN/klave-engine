"""Las tablas del plano: textos sueltos que el dibujante alineó en columnas y renglones.

Un plano no dice «esto es una tabla»: son textos. Esta lectura la reconstruye desde lo único
que el dibujante sí puso, el renglón de encabezados. Los encabezados fijan las columnas; la
columna ancla (la primera, la que nombra el renglón) fija los renglones; cada texto que cae
debajo entra en la celda donde se cruzan su columna y su renglón. Lo que no cae en ninguna
celda (una nota, una unidad, el título) se queda fuera: nunca se inventa una celda.

Las posiciones son siempre las de ``ancla_texto``: el punto donde el dibujante puso el texto."""

import statistics
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel

from klave_engine.dxf.entities import NormalizedEntity
from klave_engine.estructura.asociacion import ancla_texto
from klave_engine.geometry.bbox import BBox, bbox_union_all

# Un renglón de encabezados está en una línea si sus textos difieren menos que esto (× el alto).
_TOLERANCIA_LINEA = 0.5
# Una columna ancla sigue mientras el hueco entre renglones no pase de esto (× el alto del texto).
_HUECO_MAXIMO = 2.5


class Tabla(BaseModel):
    """Una tabla leída: ``filas`` trae sólo las celdas con texto (las vacías no aparecen)."""

    encabezados: list[str]
    filas: list[dict[str, str]]
    entidades: list[str]
    hoja: str
    bbox: BBox


@dataclass(frozen=True)
class _Texto:
    """Un texto del plano ya con su posición (la de ``ancla_texto``) y su alto."""

    entidad: NormalizedEntity
    texto: str
    x: float
    y: float
    alto: float


def _limpio(texto: str) -> str:
    return " ".join(texto.split())


def _clave(texto: str) -> str:
    return _limpio(texto).casefold()


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
) -> list[Tabla]:
    """Las tablas cuyo renglón de encabezados trae todos los ``encabezados``.

    Encabezado: cada ficha del renglón es un texto igual a la ficha pedida (sin distinguir
    mayúsculas ni espacios de más), todos en una línea (a lo más media altura de diferencia)
    y dentro de la misma hoja; con varias copias
    en la misma línea cada tabla toma las fichas más cercanas a su ancla. La columna ancla
    son los textos bajo ``ancla`` (a lo más media separación entre encabezados, y más cerca
    de ella que de otro encabezado), hacia abajo mientras el hueco entre dos no pase de 2.5
    veces el alto del texto; cada uno es un renglón. Cada otro texto debajo del encabezado
    entra en el renglón más cercano por ``y`` (a lo más media separación entre renglones) y
    en el encabezado más cercano por ``x`` (a lo más media separación entre encabezados).

    ``fila_valida`` dice qué textos de la columna ancla son renglón de verdad. Un texto que
    no lo es (un «No.», una unidad) sigue ocupando su lugar —lo que cae junto a él es suyo y
    se descarta con él— pero no es fila ni deja sus celdas a la fila de al lado. Sin él, todo
    texto de la columna ancla es renglón. Una tabla sin renglones no se devuelve."""
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

    anclas = sorted(
        candidatos.get(_clave(ancla), []),
        key=lambda t: (hoja(t.entidad), -t.y, t.x),
    )
    usados: set[str] = set()
    tablas: list[Tabla] = []
    for a in anclas:
        if a.entidad.entity_id in usados:
            continue
        cabecera = _cabecera(a, encabezados, ancla, candidatos, usados, hoja)
        if cabecera is None:
            continue
        tabla = _leer_una(cabecera, a, encabezados, ancla, todos, hoja, usados, fila_valida)
        if tabla is not None:
            tablas.append(tabla)
            usados.update(tabla.entidades)
    return tablas


def _cabecera(
    a: _Texto,
    encabezados: tuple[str, ...],
    ancla: str,
    candidatos: dict[str, list[_Texto]],
    usados: set[str],
    hoja: Callable[[NormalizedEntity], str],
) -> dict[str, _Texto] | None:
    """Los textos del renglón de encabezados que parte de ``a``, o ``None`` si falta alguno."""
    cabecera: dict[str, _Texto] = {ancla: a}
    elegidos = {a.entidad.entity_id}
    hoja_a = hoja(a.entidad)
    for h in encabezados:
        if h == ancla:
            continue
        posibles = [
            t
            for t in candidatos.get(_clave(h), [])
            if t.entidad.entity_id not in usados
            and t.entidad.entity_id not in elegidos
            and abs(t.y - a.y) <= _TOLERANCIA_LINEA * a.alto
            and hoja(t.entidad) == hoja_a
        ]
        if not posibles:
            return None
        mejor = min(posibles, key=lambda t: abs(t.x - a.x))
        cabecera[h] = mejor
        elegidos.add(mejor.entidad.entity_id)
    return cabecera


def _leer_una(
    cabecera: dict[str, _Texto],
    a: _Texto,
    encabezados: tuple[str, ...],
    ancla: str,
    todos: list[_Texto],
    hoja: Callable[[NormalizedEntity], str],
    usados: set[str],
    fila_valida: Callable[[str], bool] | None,
) -> Tabla | None:
    fichas = list(cabecera.values())
    alto = _mediana([t.alto for t in fichas])
    y_cabecera = _mediana([t.y for t in fichas])
    xs = sorted(t.x for t in fichas)
    separaciones = [b - a_ for a_, b in zip(xs, xs[1:], strict=False)]
    tolerancia_x = (_mediana(separaciones) if separaciones else 6 * alto) / 2
    cabecera_ids = {t.entidad.entity_id for t in fichas}

    def columna(t: _Texto) -> str | None:
        """El encabezado más cercano por ``x``, si está a lo más a media separación."""
        nombre, ficha = min(cabecera.items(), key=lambda kv: abs(kv[1].x - t.x))
        return nombre if abs(ficha.x - t.x) <= tolerancia_x else None

    # Todo lo que cuelga de este renglón de encabezados: en su hoja, bajo él, sin usar.
    debajo: list[_Texto] = []
    for t in todos:
        if t.entidad.entity_id in usados or t.entidad.entity_id in cabecera_ids:
            continue
        if t.y >= y_cabecera - _TOLERANCIA_LINEA * alto:
            continue
        if columna(t) is None:
            continue
        debajo.append(t)
    hoja_a = hoja(a.entidad)
    debajo = [t for t in debajo if hoja(t.entidad) == hoja_a]

    # La columna ancla: hacia abajo mientras los huecos no pasen de 2.5 veces el alto.
    renglones: list[_Texto] = []
    previo = y_cabecera
    for t in sorted((t for t in debajo if columna(t) == ancla), key=lambda t: (-t.y, t.x)):
        if previo - t.y > _HUECO_MAXIMO * alto:
            break
        if renglones and renglones[-1].y - t.y <= _TOLERANCIA_LINEA * alto:
            continue  # el mismo renglón escrito dos veces: vale el primero
        if _clave(t.texto) == _clave(ancla):
            break  # el encabezado de otra copia debajo
        renglones.append(t)
        previo = t.y
    if not renglones:
        return None

    pasos = [b.y - a_.y for a_, b in zip(renglones, renglones[1:], strict=False)]
    tolerancia_y = (_mediana([-p for p in pasos]) if pasos else 2 * alto) / 2

    celdas: list[dict[str, list[_Texto]]] = [{} for _ in renglones]
    propios = {r.entidad.entity_id for r in renglones}
    for t in debajo:
        nombre = columna(t)
        if nombre == ancla or nombre is None or t.entidad.entity_id in propios:
            continue
        i = min(range(len(renglones)), key=lambda k: abs(renglones[k].y - t.y))
        if abs(renglones[i].y - t.y) <= tolerancia_y:
            celdas[i].setdefault(nombre, []).append(t)

    filas: list[dict[str, str]] = []
    usadas: list[_Texto] = list(fichas)
    for renglon, contenido in zip(renglones, celdas, strict=True):
        if fila_valida is not None and not fila_valida(renglon.texto):
            continue
        fila = {ancla: renglon.texto}
        usadas.append(renglon)
        for nombre in encabezados:
            if nombre in contenido:
                celda = sorted(contenido[nombre], key=lambda t: (t.x, -t.y))
                fila[nombre] = " ".join(t.texto for t in celda)
                usadas.extend(celda)
        filas.append(fila)
    if not filas:
        return None
    return Tabla(
        encabezados=list(encabezados),
        filas=filas,
        entidades=[t.entidad.entity_id for t in usadas],
        hoja=hoja_a,
        bbox=bbox_union_all(t.entidad.bbox for t in usadas),
    )
