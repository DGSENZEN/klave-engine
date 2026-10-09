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
# Una celda está sobre la línea de su renglón si dista de él a lo más el mayor de: media altura
# del texto (el del renglón o el de la celda) y esta parte del paso entre renglones.
_TOLERANCIA_CELDA_EN_PASOS = 0.3
# Una columna ancla sigue mientras el hueco entre renglones no pase de esto (× el paso entre
# renglones que se observa, o el alto del texto si no se puede observar).
_HUECO_MAXIMO = 2.5
# Después de un corte, un renglón que aparece hasta a esto (× el paso) todavía se considera
# parte de la tabla —renglones en blanco en medio—: no se lee, pero se avisa.
_ALCANCE_DEL_HUECO_EN_PASOS = 10
# El paso entre renglones se mide con los huecos entre los primeros textos de la columna ancla.
_TEXTOS_PARA_EL_PASO = 9
# Una etiqueta de renglón es corta: «3», «VAR 9», «#3 (3/8")». Una nota o una leyenda no.
_MAX_PALABRAS_ETIQUETA = 4
_MAX_LARGO_ETIQUETA = 24
# Fuera de la tabla, por la derecha, se mira hasta esto (× la separación entre encabezados).
_ALCANCE_A_LA_DERECHA = 3
_CIFRA = re.compile(r"\d")


def fila_para_avisar(texto: str, entre_filas_que_si_se_leen: bool) -> bool:
    """Si una fila de la columna ancla que no se lee debe avisarse: trae cifras y es corta (una
    etiqueta: «VAR 9», «#9», «2.50», «3/16"») o está entre filas que sí se leen. Una nota larga
    debajo de la tabla no."""
    if not _CIFRA.search(texto):
        return False
    corta = len(texto) <= _MAX_LARGO_ETIQUETA and len(texto.split()) <= _MAX_PALABRAS_ETIQUETA
    return corta or entre_filas_que_si_se_leen


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
    entre dos no pase de ``hueco_maximo`` veces el paso entre renglones; cada uno es un
    renglón. El paso es el que se observa entre los primeros textos de la columna (si no hay
    bastantes, el alto del texto). Una celda es un texto de una línea (o varios en la misma
    línea, unidos de izquierda a derecha); las celdas de varias líneas todavía no se leen.
    Cada otro texto debajo del encabezado entra en la celda del encabezado más cercano por
    ``x`` (a lo más media separación entre encabezados) y del renglón más cercano por ``y`` si
    está sobre su línea: a lo más media altura de su texto (o del renglón, el mayor) o 0.3
    veces el paso, lo que sea más.

    Lo que no entra en ninguna celda no se descarta en silencio: un texto con cifras dentro
    de la tabla (bajo el encabezado, hasta medio paso después de la última fila, y a la
    derecha de la última columna hasta tres separaciones) que cae entre columnas, fuera de la
    línea de toda fila o después de un hueco se anota en ``Tabla.sin_celda``, igual que una
    fila descartada con cifras. Después de un hueco se mira hasta 10 pasos hacia abajo (o
    hasta el siguiente encabezado igual al ancla): los renglones que siguen se anotan con sus
    celdas, aunque no se lean.

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
        encontrada = _cabecera(a, encabezados, ancla, candidatos, usados, hoja)
        if encontrada.avisos:
            fichas = encontrada.fichas.values()
            tablas.append(
                Tabla(
                    encabezados=list(encabezados),
                    filas=[],
                    entidades=[t.id for t in fichas],
                    hoja=hoja(a.entidad),
                    bbox=bbox_union_all(t.entidad.bbox for t in fichas),
                    avisos=encontrada.avisos,
                )
            )
            continue
        if len(encontrada.fichas) < len(encabezados):
            continue  # un «VARILLA» suelto en el plano, no un renglón de encabezados
        tabla = _leer_una(
            encontrada, a, encabezados, ancla, todos, hoja, usados, fila_valida, hueco_maximo
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


@dataclass
class _Cabecera:
    """El renglón de encabezados que parte de un ancla: sus fichas, sus avisos y dónde empieza
    la tabla vecina de la derecha."""

    fichas: dict[str, _Texto]
    avisos: list[str]
    derecha: float


def _cabecera(
    a: _Texto,
    encabezados: tuple[str, ...],
    ancla: str,
    candidatos: dict[str, list[_Texto]],
    usados: set[str],
    hoja: Callable[[NormalizedEntity], str],
) -> _Cabecera:
    """El renglón de encabezados que parte de ``a``, en orden de izquierda a derecha.

    Sin avisos y con todas las fichas, el renglón está completo; sin avisos y con fichas de
    menos no hubo renglón (``a`` está suelto)."""
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
    fichas: dict[str, _Texto] = {ancla: a}
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
                    f"no hay «{h}» {lado} de «{_nombre_de(fichas, previo)}» en su línea"
                )
                break
            fichas[h] = previo = posibles[0]
        if avisos:
            break
    if avisos:
        # Sólo se avisa si el dibujante llegó a escribir al menos la mitad del renglón.
        presentes = sum(1 for ts in en_linea.values() if ts)
        if 2 * presentes < len(en_linea):
            return _Cabecera({}, [], derecha)
        return _Cabecera(fichas, avisos, derecha)

    # Una ficha que aparece otra vez junto a la elegida no se puede distinguir: no se adivina.
    # Entre sus vecinas, y la primera o la última, hasta tres separaciones hacia afuera.
    nombres_en_orden = list(encabezados)
    xs = sorted(t.x for t in fichas.values())
    separaciones = [b - a_ for a_, b in zip(xs, xs[1:], strict=False)]
    alcance = _ALCANCE_A_LA_DERECHA * _mediana(separaciones) if separaciones else math.inf
    for k, h in enumerate(nombres_en_orden):
        if h == ancla:
            continue
        elegida = fichas[h]
        antes = fichas[nombres_en_orden[k - 1]].x if k > 0 else elegida.x - alcance
        despues = (
            fichas[nombres_en_orden[k + 1]].x
            if k < len(nombres_en_orden) - 1
            else elegida.x + alcance
        )
        if any(
            t.id != elegida.id and min(antes, despues) < t.x < max(antes, despues)
            for t in en_linea[h]
        ):
            vecinas = " y ".join(
                f"«{nombres_en_orden[j]}»" for j in (k - 1, k + 1) if 0 <= j < len(nombres_en_orden)
            )
            avisos.append(
                f"el renglón de encabezados que empieza en «{ancla}» es ambiguo: «{h}» aparece "
                f"dos veces junto a {vecinas}"
            )
    return _Cabecera(fichas, avisos, derecha)


def _nombre_de(cabecera: dict[str, _Texto], texto: _Texto) -> str:
    return next(h for h, t in cabecera.items() if t is texto)


def _leer_una(
    encontrada: _Cabecera,
    a: _Texto,
    encabezados: tuple[str, ...],
    ancla: str,
    todos: list[_Texto],
    hoja: Callable[[NormalizedEntity], str],
    usados: set[str],
    fila_valida: Callable[[str], bool] | None,
    hueco_maximo: float,
) -> Tabla | None:
    cabecera = encontrada.fichas
    fichas = list(cabecera.values())
    alto = _mediana([t.alto for t in fichas])
    y_cabecera = _mediana([t.y for t in fichas])
    xs = sorted(t.x for t in fichas)
    separaciones = [b - a_ for a_, b in zip(xs, xs[1:], strict=False)]
    separacion = _mediana(separaciones) if separaciones else 6 * alto
    tolerancia_x = separacion / 2
    linea = _TOLERANCIA_LINEA * alto
    cabecera_ids = {t.id for t in fichas}
    hoja_a = hoja(a.entidad)
    derecho = min(xs[-1] + _ALCANCE_A_LA_DERECHA * separacion, encontrada.derecha - 1e-9)

    def columna(t: _Texto) -> str | None:
        """El encabezado más cercano por ``x``, si está a lo más a media separación."""
        nombre, ficha = min(cabecera.items(), key=lambda kv: abs(kv[1].x - t.x))
        return nombre if abs(ficha.x - t.x) <= tolerancia_x else None

    # Todo lo que cuelga de este renglón de encabezados: bajo él, en su hoja y sin usar; dentro
    # de lo ancho de la tabla, o a su derecha hasta donde alcanza la vista.
    candidatos = [
        t
        for t in todos
        if t.id not in usados
        and t.id not in cabecera_ids
        and t.y < y_cabecera - linea
        and xs[0] - tolerancia_x <= t.x <= max(xs[-1] + tolerancia_x, derecho)
    ]
    candidatos = [t for t in candidatos if hoja(t.entidad) == hoja_a]
    debajo = [t for t in candidatos if t.x <= xs[-1] + tolerancia_x]
    a_la_derecha = [t for t in candidatos if t.x > xs[-1] + tolerancia_x]

    # El paso entre renglones se observa en los primeros textos de la columna ancla: sus huecos
    # (sin contar un renglón repetido ni un salto enorme) y su altura mandan, no los del
    # encabezado, que puede ser más chico.
    en_ancla = sorted((t for t in debajo if columna(t) == ancla), key=lambda t: (-t.y, t.x))
    primeros = en_ancla[:_TEXTOS_PARA_EL_PASO]
    alto_estimado = max(alto, _mediana([t.alto for t in primeros])) if primeros else alto
    huecos = [p.y - q.y for p, q in zip(primeros, primeros[1:], strict=False)]
    utiles = [g for g in huecos if _TOLERANCIA_LINEA * alto_estimado < g <= 6 * alto_estimado]
    paso_observado = _mediana(utiles) if len(utiles) >= 2 else None
    limite_hueco = hueco_maximo * (paso_observado or alto_estimado)

    # La columna ancla: hacia abajo mientras los huecos no pasen del límite.
    renglones: list[_Texto] = []
    resto: list[_Texto] = []  # lo que sigue en la columna ancla después de un hueco
    previo = y_cabecera
    for k, t in enumerate(en_ancla):
        if previo - t.y > limite_hueco:
            resto = en_ancla[k:]
            break
        if renglones and renglones[-1].y - t.y <= _TOLERANCIA_LINEA * max(
            t.alto, renglones[-1].alto
        ):
            continue  # el mismo renglón escrito dos veces: vale el primero
        if _clave(t.texto) == _clave(ancla):
            break  # el encabezado de otra copia debajo
        renglones.append(t)
        previo = t.y
    pasos = [p.y - q.y for p, q in zip(renglones, renglones[1:], strict=False)]
    paso = _mediana(pasos) if pasos else (paso_observado or 2 * alto_estimado)

    def es_valido(texto: str) -> bool:
        return fila_valida is None or fila_valida(texto)

    # Después de un hueco la tabla puede seguir: no se lee, pero lo que sigue —renglones que
    # sí lo son— se anota, con la vista hasta ``_ALCANCE_DEL_HUECO_EN_PASOS`` pasos.
    tras_hueco: list[_Texto] = []
    ultimo = previo
    for t in resto:
        limite = limite_hueco if tras_hueco else _ALCANCE_DEL_HUECO_EN_PASOS * paso
        if ultimo - t.y > limite or _clave(t.texto) == _clave(ancla):
            break
        # El primer renglón después del hueco debe ser de los que se leen; los que le siguen
        # también pueden ser una etiqueta que no se lee («VAR 9»). Una nota o una unidad
        # no es un renglón que falte.
        if es_valido(t.texto) or (tras_hueco and fila_para_avisar(t.texto, False)):
            tras_hueco.append(t)
            ultimo = t.y
    if not renglones and not tras_hueco:
        return None

    tolerancia_y = paso / 2
    validos = [r for r in renglones if es_valido(r.texto)]
    ultima_fila = tras_hueco[-1] if tras_hueco else (validos or renglones or [a])[-1]
    y_fin = ultima_fila.y - tolerancia_y  # más abajo ya no es de la tabla
    fin_de_la_cadena = renglones[-1].y if renglones else y_cabecera

    def sobre_la_linea(renglon: _Texto, t: _Texto) -> bool:
        """Si ``t`` está sobre la línea de ``renglon``: media altura del mayor de los dos
        textos, o 0.3 pasos, lo que sea más (con un pelo de margen por el redondeo)."""
        tolerancia = max(
            _TOLERANCIA_LINEA * max(renglon.alto, t.alto), _TOLERANCIA_CELDA_EN_PASOS * paso
        )
        return abs(renglon.y - t.y) <= tolerancia * 1.001

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
            if sobre_la_linea(renglones[i], t):
                celdas[i].setdefault(nombre, []).append(t)
            else:
                anotar(t, "fuera_de_renglon", nombre)
    for t in a_la_derecha:  # una columna que el encabezado no nombra
        if t.y >= y_fin:
            anotar(t, "fuera_de_columna", None)

    filas: list[dict[str, str]] = []
    usadas: list[_Texto] = list(fichas)
    ultimo_valido = max((i for i, r in enumerate(renglones) if es_valido(r.texto)), default=-1)
    for i, (renglon, contenido) in enumerate(zip(renglones, celdas, strict=True)):
        if not es_valido(renglon.texto):
            if fila_para_avisar(renglon.texto, i < ultimo_valido):
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
