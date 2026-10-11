"""La forma real de cada entidad, para medir distancias a lo dibujado y no a su caja (R146).

Un texto es el rectángulo de sus letras, girado con él; una línea, su trazo; una polilínea cerrada
(por su bandera o porque su último punto vuelve al primero) o un sombreado, la región que encierra;
un círculo, su disco; un bloque (INSERT), lo que dibuja: sus hijos explotados. La caja sólo sirve
para preseleccionar en el índice espacial."""

import math
from collections import defaultdict
from collections.abc import Iterable

from shapely.geometry import GeometryCollection, LineString, Point, Polygon, box
from shapely.geometry.base import BaseGeometry

from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.dxf.text_extent import esquinas_de_texto

# Un punto final a menos de esto (relativo al tamaño de la polilínea) del primero la cierra.
_CIERRE_RELATIVO = 1e-6


def cerrada_por_geometria(e: NormalizedEntity) -> bool:
    """Una polilínea cerrada por su bandera, o porque su último vértice vuelve al primero (PRUEBA-1
    dibuja 177 castillos así: cinco vértices, sin la bandera)."""
    if e.entity_type != EntityType.polyline or not e.points or len(e.points) < 4:
        return e.is_closed
    if e.is_closed:
        return True
    x0, y0, x1, y1 = e.bbox
    tamano = max(x1 - x0, y1 - y0, 1e-12)
    return math.dist(e.points[0], e.points[-1]) <= _CIERRE_RELATIVO * tamano


def _poligono(puntos: list[tuple[float, float]]) -> BaseGeometry:
    forma = Polygon(puntos)
    if not forma.is_valid:
        forma = forma.buffer(0)
    return forma if not forma.is_empty else LineString(puntos)


def _arco(e: NormalizedEntity) -> BaseGeometry:
    p = e.properties
    cx, cy = p.get("center") or (0.0, 0.0)
    r = float(p.get("radius") or 0.0)
    a0, a1 = float(p.get("start_angle") or 0.0), float(p.get("end_angle") or 0.0)
    if a1 <= a0:
        a1 += 360.0
    pasos = max(2, int((a1 - a0) / 5) + 1)
    return LineString(
        [
            (cx + r * math.cos(math.radians(a0 + (a1 - a0) * k / (pasos - 1))),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * k / (pasos - 1))))
            for k in range(pasos)
        ]
    )  # fmt: skip


class Formas:
    """Las formas reales de un conjunto de entidades, calculadas una vez; los hijos de cada
    bloque se encuentran por su ``parent_insert``."""

    def __init__(self, entidades: Iterable[NormalizedEntity]) -> None:
        self._cache: dict[str, BaseGeometry] = {}
        self._hijos: dict[tuple[str, str], list[NormalizedEntity]] = defaultdict(list)
        for e in entidades:
            padre = e.properties.get("parent_insert")
            if padre:
                self._hijos[(e.source_file, str(padre))].append(e)

    def de(self, e: NormalizedEntity) -> BaseGeometry:
        forma = self._cache.get(e.entity_id)
        if forma is None:
            forma = self._calcular(e, set())
            self._cache[e.entity_id] = forma
        return forma

    def distancia(self, a: NormalizedEntity, b: NormalizedEntity) -> float:
        """La distancia entre lo que dibujan ``a`` y ``b`` (0 si se tocan o una contiene a la
        otra)."""
        return float(self.de(a).distance(self.de(b)))

    def hijos(self, e: NormalizedEntity) -> list[NormalizedEntity]:
        return list(self._hijos.get((e.source_file, e.raw_handle), []))

    def _calcular(self, e: NormalizedEntity, vistos: set[str]) -> BaseGeometry:
        tipo = e.entity_type
        puntos = [(float(q[0]), float(q[1])) for q in e.points or []]
        if e.is_textual:
            return _poligono(esquinas_de_texto(e))
        if tipo == EntityType.circle and e.properties.get("center") is not None:
            cx, cy = e.properties["center"]
            return Point(float(cx), float(cy)).buffer(float(e.properties.get("radius") or 0.0), 32)
        if tipo == EntityType.arc and e.properties.get("center") is not None:
            return _arco(e)
        if (
            tipo in (EntityType.polyline, EntityType.hatch)
            and len(puntos) >= 3
            and (tipo == EntityType.hatch or cerrada_por_geometria(e))
        ):
            return _poligono(puntos)
        if len(puntos) >= 2:
            return LineString(puntos)
        if len(puntos) == 1:
            return Point(puntos[0])
        if tipo == EntityType.insert and e.entity_id not in vistos:
            vistos.add(e.entity_id)
            formas = [self._calcular(h, vistos) for h in self.hijos(e)]
            formas = [f for f in formas if not f.is_empty]
            if formas:
                return GeometryCollection(formas)
        return box(*e.bbox)
