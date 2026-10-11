"""Beam tag detection: beam-pattern text associated with the line it dimensions (R146).

A tag takes a straight run of a line ALIGNED with it (±15°), that runs alongside it (the tag's
extent reaches the run's span, or within one text height past its end), measured to the real
geometry (the rectangle of its letters to the run's segment; the index's boxes only preselect).
Among the aligned runs within the search radius the nearest wins; the layer preference only
decides among runs about as near as it (``layer_tolerance``): the family's own layers first, then
the wall it sits on (a dala crowns a masonry wall), then any beam layer. A run shorter or longer
than a beam (``min_beam_length``, ``max_beam_length``) is taken only on those first two (a
cerramiento over a window, a contratrabe drawn across the whole building). With no aligned run
in range the tag has no span, and says so.

Then the lines are settled together: a run one family's tags take is never another family's;
the two faces of one beam are one beam line, measured on its axis; and a line several tags of
one kind take is partitioned among them, cut at the castillos and columns on it, else halfway
between consecutive tags, so it counts once."""

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel, Field
from shapely.geometry import LineString, Polygon
from shapely.geometry.base import BaseGeometry

from klave_engine.common.ids import IdGenerator
from klave_engine.detection.confidence import NEAR_LINE, SEMANTIC_LAYER, model_for
from klave_engine.detection.results import (
    Detection,
    DetectionType,
    DetectorOutput,
    layer_matches,
    make_detection,
)
from klave_engine.detection.taxonomy import familia_de_viga
from klave_engine.detection.text_patterns import TextPatternConfig, match_category
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.dxf.text_extent import alto_de_texto, esquinas_de_texto
from klave_engine.geometry.bbox import Point
from klave_engine.geometry.forma import Formas
from klave_engine.geometry.spatial_index import SpatialIndex


class BeamDetectorConfig(BaseModel):
    line_search_radius: float = 30.0
    min_beam_length: float = 50.0
    # Spans above this are axes or borders, not trabes (scaled per unit preset).
    max_beam_length: float = 1e12
    layer_hints: list[str] = Field(
        default_factory=lambda: [
            "BEAM", "GIRD", "TRABE", "VIGA", "CADENA", "CERRAM", "DALA",
        ]
    )
    avoid_layer_hints: list[str] = Field(default_factory=lambda: ["GRID", "EJE", "EJES", "AXIS"])
    # R146: a run counts as aligned with its tag within this angle.
    alignment_tolerance_deg: float = 15.0
    # R146: runs this much farther than the nearest aligned one are not as near: the layer
    # preference only chooses among the nearest within this (scaled per unit preset).
    layer_tolerance: float = 1.5
    # R146: each family's own layers, first the ones that are the element itself, then the ones
    # it sits on (a dala crowns a masonry wall; a contratrabe runs under a concrete wall).
    family_layer_hints: dict[str, list[list[str]]] = Field(
        default_factory=lambda: {
            "trabe": [["TRABE", "VIGA", "BEAM", "GIRD"], []],
            "contratrabe": [["CONTRATRABE"], ["MURO CONCRETO"]],
            # A dala crowns its masonry wall: the wall's run is the dala's own (R165: a dala on a
            # 0.6 m wall between two castillos is that wall's piece, Marina ES-100 CE-1).
            "dala": [["CADENA", "DALA", "MURO"], []],
            "cerramiento": [["CERRAM"], ["MURO"]],
        }
    )
    # R146: two lines this far apart or nearer (scaled per unit preset), parallel and overlapping
    # this share of the shorter, chosen by one beam's tags, are its two faces: one beam line.
    max_face_gap: float = 10.5
    min_face_overlap: float = 0.8
    # R146: a castillo or column whose marker reaches this near a beam line is a support on it:
    # a shared line is cut there (scaled per unit preset).
    support_tolerance: float = 1.5


@dataclass(frozen=True)
class Tramo:
    """A straight run of a line: consecutive segments in one direction (±1°)."""

    linea: NormalizedEntity
    indice: int
    p: Point
    q: Point
    largo: float

    @property
    def direccion(self) -> Point:
        dx, dy = self.q[0] - self.p[0], self.q[1] - self.p[1]
        largo = math.hypot(dx, dy) or 1.0
        return (dx / largo, dy / largo)

    @property
    def clave(self) -> tuple[str, int]:
        return (self.linea.entity_id, self.indice)


_MISMA_DIRECCION = math.radians(1.0)


def tramos_rectos(linea: NormalizedEntity) -> list[Tramo]:
    """The straight runs of an open line or polyline (an L-shaped wall is two runs)."""
    puntos = [(float(q[0]), float(q[1])) for q in linea.points or []]
    segmentos = [(a, b) for a, b in zip(puntos, puntos[1:], strict=False) if math.dist(a, b) > 0]
    tramos: list[Tramo] = []
    k = 0
    while k < len(segmentos):
        a, b = segmentos[k]
        angulo = math.atan2(b[1] - a[1], b[0] - a[0])
        j = k
        while j + 1 < len(segmentos):
            c, d = segmentos[j + 1]
            otro = math.atan2(d[1] - c[1], d[0] - c[0])
            if abs((otro - angulo + math.pi) % (2 * math.pi) - math.pi) > _MISMA_DIRECCION:
                break
            j += 1
        largo = sum(math.dist(s, t) for s, t in segmentos[k : j + 1])
        tramos.append(Tramo(linea, len(tramos), segmentos[k][0], segmentos[j][1], largo))
        k = j + 1
    return tramos


@dataclass(frozen=True)
class _Candidata:
    """An aligned run a tag may dimension: its layer preference (0 the family's own layer, 1 the
    layer it sits on, 2 any beam layer, 3 other), its real distance to the tag, where the tag lies
    along it (``t0``–``t1``, from ``p``) and the run."""

    preferencia: int
    distancia: float
    tramo: Tramo
    t0: float
    t1: float


def detect_beams(
    entities: list[NormalizedEntity],
    index: SpatialIndex,
    config: BeamDetectorConfig | None = None,
    text_config: TextPatternConfig | None = None,
    detection_ids: IdGenerator | None = None,
    supports: DetectorOutput | None = None,
) -> DetectorOutput:
    """Every beam tag with the run it dimensions. ``supports`` (the column detector's output)
    gives the castillos and columns where a line shared by several tags is cut (R146)."""
    config = config or BeamDetectorConfig()
    text_config = text_config or TextPatternConfig()
    detection_ids = detection_ids or IdGenerator("det")
    output = DetectorOutput(detector_name="beam_detector")
    model = model_for("beam_tag")
    formas = Formas(entities)
    tramos_de: dict[str, list[Tramo]] = {}
    marcadas: list[_Marcada] = []

    for entity in entities:
        if not entity.is_textual or not entity.text:
            continue
        if match_category(entity.text, text_config, "beam_tag") is None:
            continue

        notes = [f"Text '{entity.text.strip()}' matched beam tag pattern"]
        source_entities = [entity.entity_id]
        properties: dict = {}
        features: dict[str, float] = {}
        familia = familia_de_viga(entity.text).value

        # The trabe's own line: an aligned straight run beside the tag, never a grid axis nor a
        # leader's lines (R135), measured to what is drawn (R146).
        candidatas: list[_Candidata] = []
        for hit in index.entities_near_entity(entity.entity_id, config.line_search_radius):
            other = index.get(hit.entity_id)
            if other.entity_type not in (EntityType.line, EntityType.polyline):
                continue
            if other.is_closed or not other.points or other.is_annotation:
                continue
            if layer_matches(other.layer, config.avoid_layer_hints):
                continue
            if other.entity_id not in tramos_de:
                tramos_de[other.entity_id] = tramos_rectos(other)
            tramos = tramos_de[other.entity_id]
            candidatas.extend(_alineadas(entity, familia, tramos, formas, config))
        elegida, dudoso = _tramo_de_la_trabe(candidatas, entity, config)
        marcadas.append(
            _Marcada(len(output.detections), entity, familia, _clase(entity.text, familia),
                     candidatas, elegida)
        )  # fmt: skip
        if elegida is not None:
            tramo = elegida.tramo
            features[NEAR_LINE] = 1.0
            source_entities.append(tramo.linea.entity_id)
            properties["estimated_span_length"] = round(tramo.largo, 3)
            properties["span_layer"] = tramo.linea.layer
            properties["span_run"] = [_redondo(tramo.p), _redondo(tramo.q)]
            properties["span_distance"] = round(elegida.distancia, 4)
            notes.append(
                f"Associated with linework of length {tramo.largo:.1f} "
                f"(tramo alineado a {elegida.distancia:.3f} de la etiqueta)"
            )
            if layer_matches(tramo.linea.layer, config.layer_hints):
                notes.append(f"Línea de trabe en capa {tramo.linea.layer}")
            if dudoso is not None:
                properties["claro_dudoso"] = dudoso
                notes.append(dudoso)
        else:
            sin_claro = (
                "longitud: ninguna línea alineada con la etiqueta (±"
                f"{config.alignment_tolerance_deg:g}°) corre junto a ella a menos de "
                f"{config.line_search_radius:g} unidades; sin claro"
            )
            properties["sin_claro"] = sin_claro
            notes.append(sin_claro)

        hint_layer = entity.layer if layer_matches(entity.layer, config.layer_hints) else None
        if hint_layer is None and elegida is not None:
            if layer_matches(elegida.tramo.linea.layer, config.layer_hints):
                hint_layer = elegida.tramo.linea.layer
        if hint_layer is not None:
            features[SEMANTIC_LAYER] = 1.0

        confidence = round(model.score(features), 4)
        notes.extend(model.explain(features))
        output.detections.append(
            make_detection(
                detection_ids.next(),
                DetectionType.beam_tag,
                entity.text.strip(),
                entity.bbox,
                confidence,
                source_entities,
                "beam_tag_regex_near_linework",
                notes,
                properties,
                entity.source_file,
            )
        )
    apoyos = _apoyos(supports, index, formas)
    _repartir(marcadas, output, apoyos, config)
    return output


@dataclass
class _Marcada:
    """A beam tag while its span is decided: its detection, letters, family, the kind of element
    its mark names (a dala's CE, CI, DA…: a cadena de enrase and a cadena intermedia crown the same
    wall at two heights, never two pieces of one), its aligned candidates and the chosen one."""

    indice: int
    etiqueta: NormalizedEntity
    familia: str
    clase: str
    candidatas: list[_Candidata]
    elegida: _Candidata | None


def _clase(texto: str, familia: str) -> str:
    if familia != "dala":
        return familia
    letras = re.match(r"[A-Z]+", texto.strip().upper())
    return f"dala:{letras.group(0) if letras else ''}"


def _apoyos(
    supports: DetectorOutput | None, index: SpatialIndex, formas: Formas
) -> list[BaseGeometry]:
    """The markers of the detected castillos and columns: where a shared line is cut."""
    salida: list[BaseGeometry] = []
    for d in supports.detections if supports is not None else []:
        if d.detection_type != DetectionType.column_tag or len(d.source_entities) < 2:
            continue
        try:
            marcador = index.get(d.source_entities[1])
        except KeyError:
            continue
        salida.append(formas.de(marcador))
    return salida


def _repartir(
    marcadas: list[_Marcada],
    output: DetectorOutput,
    apoyos: list[BaseGeometry],
    config: BeamDetectorConfig,
) -> None:
    """R146 (4, 5): a line one family's tags take is never another family's (the foreign tag
    takes its next aligned run, or none); the two faces of one beam its tags take are one beam
    line; and a line several tags of one kind take is partitioned among them — cut at the
    supports between consecutive tags, else halfway — so it counts once."""
    _sin_ajenas(marcadas, output, config)
    for grupo in _por_clase(marcadas).values():
        for viga in _vigas(grupo, config):
            _partir(viga, output, apoyos, config)


def _por_clase(marcadas: list[_Marcada]) -> dict[tuple[str, str], list[_Marcada]]:
    grupos: dict[tuple[str, str], list[_Marcada]] = {}
    for m in marcadas:
        if m.elegida is not None:
            grupos.setdefault((m.familia, m.clase), []).append(m)
    return grupos


def _sin_ajenas(
    marcadas: list[_Marcada], output: DetectorOutput, config: BeamDetectorConfig
) -> None:
    """A run taken by tags of several families belongs to the family that prefers its layer
    most (then the nearest tag); the others take their next aligned run not owned by another
    family, or no span with an aviso."""
    excluidas: dict[int, set[tuple[str, int]]] = {}
    for _vuelta in range(4):
        por_tramo: dict[tuple[str, int], list[_Marcada]] = {}
        for m in marcadas:
            if m.elegida is not None:
                por_tramo.setdefault(m.elegida.tramo.clave, []).append(m)
        cambio = False
        for clave, ms in por_tramo.items():
            if len({m.familia for m in ms}) < 2:
                continue
            assert all(m.elegida is not None for m in ms)
            duena = min(
                ms,
                key=lambda m: (m.elegida.preferencia, m.elegida.distancia),  # type: ignore[union-attr]
            ).familia
            for m in ms:
                if m.familia == duena:
                    continue
                excluidas.setdefault(m.indice, set()).add(clave)
                restantes = [c for c in m.candidatas if c.tramo.clave not in excluidas[m.indice]]
                m.elegida, dudoso = _tramo_de_la_trabe(restantes, m.etiqueta, config)
                d = output.detections[m.indice]
                aviso = (
                    f"claro: la línea {clave[0]} junto a la etiqueta es de otra familia ({duena}); "
                    "no se toma"
                )
                d.evidence.notes.append(aviso)
                _poner_tramo(d, m.elegida, dudoso, aviso)
                cambio = True
        if not cambio:
            break


def _poner_tramo(d: Detection, elegida: _Candidata | None, dudoso: str | None, motivo: str) -> None:
    """Rewrite a detection's span after its run changed."""
    props = d.properties
    for clave in ("estimated_span_length", "span_layer", "span_run", "span_distance"):
        props.pop(clave, None)
    props.pop("claro_dudoso", None)
    d.source_entities = d.source_entities[:1]
    if elegida is None:
        props["sin_claro"] = f"longitud: {motivo}; ninguna otra línea alineada junto a ella"
        return
    tramo = elegida.tramo
    d.source_entities.append(tramo.linea.entity_id)
    props["estimated_span_length"] = round(tramo.largo, 3)
    props["span_layer"] = tramo.linea.layer
    props["span_run"] = [_redondo(tramo.p), _redondo(tramo.q)]
    props["span_distance"] = round(elegida.distancia, 4)
    if dudoso is not None:
        props["claro_dudoso"] = dudoso


@dataclass
class _Viga:
    """One beam line: the runs its tags took (one, or the two faces of the beam), its axis
    (``origen`` + ``u``), its span along the axis (``inicio``–``fin``), the band its faces span
    across it, and its tags with where each lies along the axis."""

    tramos: list[Tramo]
    origen: Point
    u: Point
    inicio: float
    fin: float
    banda: tuple[float, float]
    marcadas: list[tuple[float, _Marcada]]


def _a_lo_largo(origen: Point, u: Point, p: Point) -> tuple[float, float]:
    """A point's place along the axis and across it."""
    dx, dy = p[0] - origen[0], p[1] - origen[1]
    return dx * u[0] + dy * u[1], -dx * u[1] + dy * u[0]


def _vigas(grupo: list[_Marcada], config: BeamDetectorConfig) -> list[_Viga]:
    """The beam lines of one kind of tag: its chosen runs, the two faces of one beam merged
    (``_caras_de_una_viga``)."""
    tramos: dict[tuple[str, int], Tramo] = {}
    for m in grupo:
        assert m.elegida is not None
        tramos.setdefault(m.elegida.tramo.clave, m.elegida.tramo)
    claves = list(tramos)
    padre = {c: c for c in claves}

    def raiz(c: tuple[str, int]) -> tuple[str, int]:
        while padre[c] != c:
            padre[c] = padre[padre[c]]
            c = padre[c]
        return c

    for i, a in enumerate(claves):
        for b in claves[i + 1 :]:
            if _caras_de_una_viga(tramos[a], tramos[b], config):
                padre[raiz(b)] = raiz(a)
    juntas: dict[tuple[str, int], list[Tramo]] = {}
    for c in claves:
        juntas.setdefault(raiz(c), []).append(tramos[c])
    vigas: list[_Viga] = []
    for caras in juntas.values():
        base = max(caras, key=lambda t: (t.largo, _orden_de_id(t.linea.entity_id)))
        origen, u = base.p, base.direccion
        inicios, fines, cruces = [], [], []
        for t in caras:
            ta, ca = _a_lo_largo(origen, u, t.p)
            tb, cb = _a_lo_largo(origen, u, t.q)
            inicios.append(min(ta, tb))
            fines.append(max(ta, tb))
            cruces.extend([ca, cb])
        claves_caras = {t.clave for t in caras}
        suyas = []
        for m in grupo:
            assert m.elegida is not None
            if m.elegida.tramo.clave in claves_caras:
                esquinas = esquinas_de_texto(m.etiqueta)
                centro = (sum(q[0] for q in esquinas) / 4, sum(q[1] for q in esquinas) / 4)
                suyas.append((_a_lo_largo(origen, u, centro)[0], m))
        vigas.append(
            _Viga(
                caras,
                origen,
                u,
                sum(inicios) / len(inicios),
                sum(fines) / len(fines),
                (min(cruces), max(cruces)),
                sorted(suyas, key=lambda x: (x[0], x[1].indice)),
            )
        )
    return vigas


def _caras_de_una_viga(a: Tramo, b: Tramo, config: BeamDetectorConfig) -> bool:
    """Two runs are the faces of one beam when they are drawn on the same layer, parallel, at
    most ``max_face_gap`` apart and overlapping ``min_face_overlap`` of the shorter."""
    if a.linea.layer != b.linea.layer:
        return False
    ua, ub = a.direccion, b.direccion
    if abs(ua[0] * ub[0] + ua[1] * ub[1]) < math.cos(_MISMA_DIRECCION * 2):
        return False
    pa, ca = _a_lo_largo(a.p, ua, b.p)
    pb, cb = _a_lo_largo(a.p, ua, b.q)
    if max(abs(ca), abs(cb)) > config.max_face_gap or min(abs(ca), abs(cb)) <= 0.0:
        return False
    traslape = min(a.largo, max(pa, pb)) - max(0.0, min(pa, pb))
    return traslape >= config.min_face_overlap * min(a.largo, b.largo)


def _partir(
    viga: _Viga, output: DetectorOutput, apoyos: list[BaseGeometry], config: BeamDetectorConfig
) -> None:
    """Each tag of a beam line gets its own tramo: cut between consecutive tags at the support
    nearest halfway between them (a castillo or column on the line), else halfway."""
    largo_total = viga.fin - viga.inicio
    caras = [
        f"{t.largo:g}" for t in sorted(viga.tramos, key=lambda t: _orden_de_id(t.linea.entity_id))
    ]
    n = len(viga.marcadas)
    if n == 1 and len(viga.tramos) == 1:
        _al_maximo(viga.marcadas[0][1], output, config)
        return
    sobre = _apoyos_sobre(viga, apoyos, config)
    cortes: list[float] = []
    por_apoyo = 0
    for (ta, _a), (tb, _b) in zip(viga.marcadas, viga.marcadas[1:], strict=False):
        medio = (ta + tb) / 2
        entre = [t for t in sobre if ta < t < tb]
        if entre:
            cortes.append(min(entre, key=lambda t: (abs(t - medio), t)))
            por_apoyo += 1
        else:
            cortes.append(medio)
    limites = [viga.inicio, *[min(max(c, viga.inicio), viga.fin) for c in cortes], viga.fin]
    marcas = ", ".join(sorted({(m.etiqueta.text or "").strip() for _t, m in viga.marcadas}))
    for k, (_t, m) in enumerate(viga.marcadas):
        d = output.detections[m.indice]
        props = d.properties
        a, b = limites[k], limites[k + 1]
        p = (viga.origen[0] + viga.u[0] * a, viga.origen[1] + viga.u[1] * a)
        q = (viga.origen[0] + viga.u[0] * b, viga.origen[1] + viga.u[1] * b)
        props["estimated_span_length"] = round(max(b - a, 0.0), 3)
        props["span_run"] = [_redondo(p), _redondo(q)]
        for t in viga.tramos:
            if t.linea.entity_id not in d.source_entities:
                d.source_entities.append(t.linea.entity_id)
        if len(viga.tramos) > 1:
            aviso_caras = (
                f"claro de una viga dibujada con {len(viga.tramos)} caras ({', '.join(caras)}): "
                f"se mide su eje, {largo_total:.3f}"
            )
            props["claro_caras"] = aviso_caras
            d.evidence.notes.append(aviso_caras)
        if n > 1:
            como = (
                "en los apoyos entre ellas"
                if por_apoyo == n - 1
                else "a medio camino entre ellas"
                if por_apoyo == 0
                else f"en {por_apoyo} apoyo(s) y a medio camino donde no hay"
            )
            aviso = (
                f"claro compartido: tramo partido entre {n} etiquetas ({marcas}) de una línea de "
                f"{largo_total:.3f}, cortada {como}; le toca {b - a:.3f}"
            )
            props["claro_compartido"] = aviso
            d.evidence.notes.append(aviso)
        _al_maximo(m, output, config)


def _apoyos_sobre(
    viga: _Viga, apoyos: list[BaseGeometry], config: BeamDetectorConfig
) -> list[float]:
    """Where along the beam line its supports stand: markers that reach the band of its faces."""
    if not apoyos:
        return []
    o0, o1 = viga.banda
    tol = config.support_tolerance

    def punto(t: float, o: float) -> Point:
        return (
            viga.origen[0] + viga.u[0] * t - viga.u[1] * o,
            viga.origen[1] + viga.u[1] * t + viga.u[0] * o,
        )

    banda = Polygon(
        [punto(viga.inicio, o0 - tol), punto(viga.fin, o0 - tol),
         punto(viga.fin, o1 + tol), punto(viga.inicio, o1 + tol)]
    )  # fmt: skip
    salida = []
    for forma in apoyos:
        if forma.is_empty or not forma.intersects(banda):
            continue
        centro = forma.centroid
        salida.append(_a_lo_largo(viga.origen, viga.u, (centro.x, centro.y))[0])
    return sorted(salida)


def _al_maximo(m: _Marcada, output: DetectorOutput, config: BeamDetectorConfig) -> None:
    """A tag's own tramo longer than a beam is not a span (a long line no other tag shares)."""
    d = output.detections[m.indice]
    largo = d.properties.get("estimated_span_length")
    if isinstance(largo, (int, float)) and largo > config.max_beam_length:
        aviso = (
            f"longitud: su tramo de la línea mide {largo:g}, más que el máximo de una viga "
            f"({config.max_beam_length:g}); sin claro"
        )
        for clave in ("estimated_span_length", "span_run", "claro_compartido"):
            d.properties.pop(clave, None)
        d.properties["sin_claro"] = aviso
        d.evidence.notes.append(aviso)


def _redondo(p: Point) -> list[float]:
    return [round(p[0], 4), round(p[1], 4)]


def _preferencia(capa: str, familia: str, config: BeamDetectorConfig) -> int:
    listas = config.family_layer_hints.get(familia) or []
    propias = listas[0] if listas else []
    de_apoyo = listas[1] if len(listas) > 1 else []
    if propias and layer_matches(capa, propias):
        return 0
    if de_apoyo and layer_matches(capa, de_apoyo):
        return 1
    if layer_matches(capa, config.layer_hints):
        return 2
    return 3


def _alineadas(
    etiqueta: NormalizedEntity,
    familia: str,
    tramos: list[Tramo],
    formas: Formas,
    config: BeamDetectorConfig,
) -> list[_Candidata]:
    """The runs of one line that a tag may dimension: aligned with it, of a beam's length (any
    length on the family's own layers or the wall it sits on), within the search radius of its
    letters, and running alongside it."""
    giro = math.radians(etiqueta.rotation or 0.0)
    sentido = (math.cos(giro), math.sin(giro))
    alto = alto_de_texto(etiqueta)
    esquinas = esquinas_de_texto(etiqueta)
    letras = formas.de(etiqueta)
    salida: list[_Candidata] = []
    for tramo in tramos:
        ux, uy = tramo.direccion
        coseno = min(1.0, abs(ux * sentido[0] + uy * sentido[1]))
        if math.degrees(math.acos(coseno)) > config.alignment_tolerance_deg:
            continue
        preferencia = _preferencia(tramo.linea.layer, familia, config)
        # On the family's own layers (or the wall it sits on) a run is the element whatever its
        # length: a cerramiento over a window is 0.45 m (Marina ES-400 CR-1), a contratrabe may
        # run across the building. Elsewhere short runs are stubs and strokes, long ones axes,
        # borders and slab edges.
        if preferencia > 1 and not (
            config.min_beam_length <= tramo.largo <= config.max_beam_length
        ):
            continue
        distancia = float(letras.distance(LineString([tramo.p, tramo.q])))
        if distancia > config.line_search_radius:
            continue
        proyecciones = [(x - tramo.p[0]) * ux + (y - tramo.p[1]) * uy for x, y in esquinas]
        t0, t1 = min(proyecciones), max(proyecciones)
        if t1 < -alto or t0 > tramo.largo + alto:
            continue  # the tag lies past the run's end: not the line it dimensions
        salida.append(_Candidata(preferencia, distancia, tramo, t0, t1))
    return salida


# Two candidates whose lengths differ by more than this share of the longer one make the span
# doubtful when they are equally near (R135).
_CLARO_DUDOSO = 0.10


def _tramo_de_la_trabe(
    candidatas: list[_Candidata], etiqueta: NormalizedEntity, config: BeamDetectorConfig
) -> tuple[_Candidata | None, str | None]:
    """The tag's run: among the aligned runs about as near as the nearest one (within
    ``layer_tolerance``), the family's own layer, then the layer it sits on, then a beam layer,
    then the nearest; among runs equally near (within a millionth of the search radius) the one
    whose midpoint is nearest the tag's centre, then the first entity id — never the spatial
    index's order (R135). When the tied runs' lengths differ by more than 10 %, the span is
    doubtful and the aviso says so."""
    if not candidatas:
        return None, None
    cercana = min(c.distancia for c in candidatas)
    cerca = [c for c in candidatas if c.distancia <= cercana + config.layer_tolerance]
    mejor = min((c.preferencia, c.distancia) for c in cerca)
    holgura = config.line_search_radius * 1e-6
    empatadas = [
        c for c in cerca if c.preferencia == mejor[0] and c.distancia <= mejor[1] + holgura
    ]
    xs = [q[0] for q in esquinas_de_texto(etiqueta)]
    ys = [q[1] for q in esquinas_de_texto(etiqueta)]
    centro = (sum(xs) / 4, sum(ys) / 4)
    elegida = min(
        empatadas,
        key=lambda c: (
            math.dist(centro, _punto_medio([c.tramo.p, c.tramo.q])),
            _orden_de_id(c.tramo.linea.entity_id),
            c.tramo.indice,
        ),
    )
    distintas = [
        c
        for c in empatadas
        if abs(c.tramo.largo - elegida.tramo.largo)
        > _CLARO_DUDOSO * max(c.tramo.largo, elegida.tramo.largo)
    ]
    corto = _corto_de_apoyo(elegida, candidatas, config)
    if not distintas:
        return elegida, corto
    largos = ", ".join(f"{v:g}" for v in sorted({round(c.tramo.largo, 3) for c in empatadas}))
    dudoso = (
        f"claro dudoso: {len(empatadas)} líneas igual de cerca de la etiqueta, de largos "
        f"{largos}; se toma la de {round(elegida.tramo.largo, 3):g}, la de punto medio más cercano"
    )
    return elegida, dudoso if corto is None else f"{dudoso}; {corto}"


def _corto_de_apoyo(
    elegida: _Candidata, candidatas: list[_Candidata], config: BeamDetectorConfig
) -> str | None:
    """R165: a run of the wall the element sits on, shorter than a beam, may be a piece of that
    wall and not the element (Marina ES-000 CTA-3: a 0.45 m piece of MC-1's face, the wall drawn
    as closed boxes): taken, but doubtful, with the other aligned lines."""
    if elegida.preferencia != 1 or elegida.tramo.largo >= config.min_beam_length:
        return None
    otras = sorted(
        {
            f"{c.tramo.linea.layer} {round(c.tramo.largo, 3):g} a {c.distancia:.2f}"
            for c in candidatas
            if c.tramo.clave != elegida.tramo.clave
        }
    )
    return (
        f"claro dudoso: el tramo tomado mide {round(elegida.tramo.largo, 3):g}, menos que una "
        f"viga ({config.min_beam_length:g}), y es de la capa en que se apoya "
        f"({elegida.tramo.linea.layer}), no de la suya; otras líneas alineadas: "
        + ("; ".join(otras) if otras else "ninguna")
    )


def _punto_medio(puntos: Sequence[Point]) -> Point:
    """The point halfway along the line."""
    total = sum(math.dist(a, b) for a, b in zip(puntos, puntos[1:], strict=False))
    falta = total / 2
    for a, b in zip(puntos, puntos[1:], strict=False):
        tramo = math.dist(a, b)
        if tramo >= falta and tramo > 0:
            f = falta / tramo
            return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
        falta -= tramo
    return puntos[-1] if puntos else (0.0, 0.0)


def _orden_de_id(entity_id: str) -> tuple[tuple[int, int | str], ...]:
    """An entity id in its natural order: «ent_9» before «ent_10»."""
    return tuple((0, int(p)) if p.isdigit() else (1, p) for p in re.findall(r"\d+|\D+", entity_id))
