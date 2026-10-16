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
the two faces of one beam are one beam line, measured on its axis (R172: as far apart as its
definition's width plus 5 cm, else 0.35 m; the axis drawn halfway between them is the beam's
too); a line several tags of one kind take is partitioned among them, cut at the castillos and
columns on it, else halfway between consecutive tags, so it counts once; and the legs of a tag's
own polyline that no tag takes go to the tag on the leg they hang from (R173, «tramo sin etiqueta
propia»)."""

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field

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
from klave_engine.detection.schedules import ElementSpec, ScheduleInventory, family_of_mark
from klave_engine.detection.taxonomy import familia_de_viga
from klave_engine.detection.text_patterns import (
    TextPatternConfig,
    es_tipo_de_dala,
    es_tipo_sin_capa,
    match_category,
)
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
    # Grid axes, and (R152) a slab's own drawing — its joists, casetones and edges — are never a
    # beam's line (Marina: a «CI» beside its wall stood on a 5.85 m joist).
    avoid_layer_hints: list[str] = Field(
        default_factory=lambda: ["GRID", "EJE", "EJES", "AXIS", "LOSA"]
    )
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
    # R172: the width a mark's definition declares, in drawing units (the pipeline sets them from
    # the drawing's definitions before detection): its mark → its width, ``None`` when the mark's
    # own definition declares none; a mark with no definition, its family note's. Its faces may
    # lie that width plus ``face_width_margin`` (scaled per unit preset) apart, never less than
    # ``max_face_gap``: a dala's faces are its wall's (a CI of 15 cm on a 30 cm wall).
    face_widths: dict[str, float | None] = Field(default_factory=dict)
    family_face_widths: dict[str, float] = Field(default_factory=dict)
    face_width_margin: float = 1.5
    # R172: with no width declared, the beam's axis drawn on its layer halfway between two faces
    # (within this share of their gap) makes them one beam when each face lies at most
    # ``max_face_gap`` from it.
    axis_centre_tolerance: float = 0.1
    # R173: a wall's outline is never a beam's own line: its other legs are walls (the stub of a
    # crossing wall, its other face, its end), not the dala's that crowns the wall its tag labels.
    wall_layer_hints: list[str] = Field(default_factory=lambda: ["MURO"])
    # R169: the layers of a dala's tags that crown the wall they sit on, whatever their text's
    # direction.
    dala_tag_layer_hints: list[str] = Field(default_factory=lambda: ["CADENA", "DALA"])
    # R177: a dala crowns masonry: a concrete wall's layer (EST-MURO CONCRETO) is never its own.
    concrete_wall_layer_hints: list[str] = Field(
        default_factory=lambda: ["MURO CONC", "MURO DE CONC", "MURO DE CONCRETO"]
    )
    # R146: a castillo or column whose marker reaches this near a beam line is a support on it:
    # a shared line is cut there (scaled per unit preset).
    support_tolerance: float = 1.5


def con_anchos_declarados(
    config: BeamDetectorConfig, inventory: ScheduleInventory, meters_factor: float | None
) -> BeamDetectorConfig:
    """A copy of ``config`` with the width each mark's definition declares (R172), in drawing
    units: the b of its b×h, as ``apply_schedule`` would stamp it — none for a section with an
    assumed side. Without a reliable unit, none."""
    if meters_factor is None or meters_factor <= 0:
        return config

    def ancho(spec: ElementSpec) -> float | None:
        if spec.section_cm is None or spec.seccion_supuesta:
            return None
        return spec.section_cm[0] / 100.0 / meters_factor

    familias = {f: ancho(spec) for f, spec in inventory.by_family.items()}
    return config.model_copy(
        update={
            "face_widths": {marca: ancho(spec) for marca, spec in inventory.by_mark.items()},
            "family_face_widths": {f: a for f, a in familias.items() if a is not None},
        }
    )


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
        if es_tipo_sin_capa(entity.text) and not es_tipo_de_dala(entity.text, entity.layer):
            continue  # R152: a dala type tag off a dala layer is its detail's title

        notes = [f"Text '{entity.text.strip()}' matched beam tag pattern"]
        source_entities = [entity.entity_id]
        properties: dict = {}
        features: dict[str, float] = {}
        familia = familia_de_viga(entity.text).value

        # The trabe's own line: an aligned straight run beside the tag, never a grid axis nor a
        # leader's lines (R135), measured to what is drawn (R146).
        candidatas: list[_Candidata] = []
        sobre: list[_Candidata] = []
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
            if _sobre_su_muro(entity, familia, config):
                sobre.extend(_alineadas(entity, familia, tramos, formas, config, True))
        if familia == "dala":
            # R169: a trabe's line is never a dala's span.
            candidatas = [c for c in candidatas if not _de_trabe(c.tramo, config)]
        if _sobre_su_muro(entity, familia, config):
            candidatas = _del_muro(entity, candidatas, sobre, config)
        elegida, dudoso = _tramo_de_la_trabe(candidatas, entity, config)
        marcadas.append(
            _Marcada(len(output.detections), entity, familia, _clase(entity.text, familia),
                     candidatas, elegida, _ancho_declarado(entity.text, config))
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
            if _sobre_su_muro(entity, familia, config):
                sin_claro = (
                    "longitud: la etiqueta no está sobre ningún muro ni corre junto a una línea "
                    f"de su familia o de un muro a menos de {config.line_search_radius:g} "
                    "unidades (un vano, o la trabe que no es suya); sin claro"
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
    _repartir(marcadas, output, apoyos, config, index)
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
    # R172: the width its mark's definition declares (drawing units), if any.
    ancho: float | None = None


def _ancho_declarado(texto: str, config: BeamDetectorConfig) -> float | None:
    """The width the definition of a tag's mark declares: its own, else (no definition of the
    mark) its family note's — what ``apply_schedule`` stamps on it."""
    marca = texto.strip().upper()
    if marca in config.face_widths:
        return config.face_widths[marca]
    return config.family_face_widths.get(family_of_mark(marca))


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
    index: SpatialIndex | None = None,
) -> None:
    """R146 (4, 5): a line one family's tags take is never another family's (the foreign tag
    takes its next aligned run, or none); the two faces of one beam its tags take are one beam
    line; and a line several tags of one kind take is partitioned among them — cut at the
    supports between consecutive tags, else halfway — so it counts once."""
    _sin_ajenas(marcadas, output, config)
    for grupo in _por_clase(marcadas).values():
        for viga in _vigas(grupo, config, index):
            _partir(viga, output, apoyos, config)
    _sin_etiqueta_propia(marcadas, output, config, index)


def _sin_etiqueta_propia(
    marcadas: list[_Marcada],
    output: DetectorOutput,
    config: BeamDetectorConfig,
    index: SpatialIndex | None,
) -> None:
    """R173: a leg of a tag's own polyline (on its family's own layer, never a wall's outline)
    that no tag takes goes to the tag on the leg it hangs from — the one whose tramo holds that
    corner, one per kind of tag on it —, with «tramo sin etiqueta propia» (PRUEBA-1: T-7's beam
    turns 2.225 along the stair; T-9's, 1.818). A leg between two taken legs is cut halfway. Not
    a leg: one no longer than ``max_face_gap`` (the end of a beam drawn with its faces), nor one
    with a line of its layer beside it as a face, or on it (a beam drawn with both faces, a
    stretch drawn twice): those stop the polyline there."""
    tomados = {m.elegida.tramo.clave for m in marcadas if m.elegida is not None}
    por_linea: dict[str, list[_Marcada]] = {}
    for m in marcadas:
        props = output.detections[m.indice].properties
        if m.elegida is None or "estimated_span_length" not in props:
            continue
        linea = m.elegida.tramo.linea
        if _preferencia(linea.layer, m.familia, config) != 0:
            continue
        if layer_matches(linea.layer, config.wall_layer_hints):
            continue
        por_linea.setdefault(linea.entity_id, []).append(m)
    for suyas in por_linea.values():
        tramos = tramos_rectos(suyas[0].elegida.tramo.linea)  # type: ignore[union-attr]
        if len(tramos) < 2:
            continue
        tomado = [t.clave in tomados for t in tramos]
        libre = [
            not tomado[k] and _es_tramo(t, tramos, index, config) for k, t in enumerate(tramos)
        ]
        for k, t in enumerate(tramos):
            if tomado[k]:
                continue
            # The taken legs it hangs from, through free legs only, on each side.
            lados: list[tuple[int, int]] = []
            for paso in (-1, 1):
                j = k
                while 0 <= j < len(tramos) and not tomado[j] and libre[j]:
                    j += paso
                if 0 <= j < len(tramos) and tomado[j] and libre[k]:
                    lados.append((abs(j - k), j))
            if not lados:
                continue
            cerca = min(d for d, _j in lados)
            duenos = [j for d, j in lados if d == cerca]
            for j in duenos:
                esquina = tramos[j].p if k < j else tramos[j].q
                parte = t.largo / len(duenos)
                _sumar_tramo(suyas, tramos[j], esquina, t, parte, len(duenos) > 1, output)


def _es_tramo(
    t: Tramo, tramos: list[Tramo], index: SpatialIndex | None, config: BeamDetectorConfig
) -> bool:
    """R173: whether an untaken leg is a leg of the beam: longer than ``max_face_gap``, with no
    line of its layer beside it as a face or drawn on it."""
    if t.largo <= config.max_face_gap:
        return False
    otros: list[Tramo] = [r for r in tramos if r.clave != t.clave]
    if index is not None:
        tol = config.max_face_gap
        xs, ys = [t.p[0], t.q[0]], [t.p[1], t.q[1]]
        caja = (min(xs) - tol, min(ys) - tol, max(xs) + tol, max(ys) + tol)
        for hit in index.entities_in_bbox(caja):
            linea = index.get(hit.entity_id)
            if linea.entity_id == t.linea.entity_id or linea.layer != t.linea.layer:
                continue
            if linea.entity_type not in (EntityType.line, EntityType.polyline):
                continue
            if not linea.points or linea.is_annotation:
                continue
            otros.extend(tramos_rectos(linea))
    for r in otros:
        if r.linea.layer != t.linea.layer:
            continue
        ur = r.direccion
        if abs(t.direccion[0] * ur[0] + t.direccion[1] * ur[1]) < math.cos(_MISMA_DIRECCION * 2):
            continue
        cruces = [_a_lo_largo(t.p, t.direccion, r.p)[1], _a_lo_largo(t.p, t.direccion, r.q)[1]]
        if max(abs(c) for c in cruces) <= config.max_face_gap and _traslapan(t, r, config):
            return False
    return True


def _sumar_tramo(
    suyas: list[_Marcada],
    tomado: Tramo,
    esquina: Point,
    tramo: Tramo,
    parte: float,
    partido: bool,
    output: DetectorOutput,
) -> None:
    """Give an untaken leg (or its half) to the tag of each kind on the taken leg whose tramo
    holds the corner it hangs from."""
    por_clase: dict[tuple[str, str], list[_Marcada]] = {}
    for m in suyas:
        assert m.elegida is not None
        if m.elegida.tramo.clave == tomado.clave:
            por_clase.setdefault((m.familia, m.clase), []).append(m)
    for ms in por_clase.values():

        def junto(m: _Marcada) -> tuple[float, int]:
            corrida = output.detections[m.indice].properties.get("span_run") or []
            cerca = min((math.dist(esquina, (q[0], q[1])) for q in corrida), default=math.inf)
            return (cerca, m.indice)

        m = min(ms, key=junto)
        d = output.detections[m.indice]
        props = d.properties
        antes = float(props["estimated_span_length"])
        props["estimated_span_length"] = round(antes + parte, 3)
        mitad = f" (la mitad, {parte:.3f}: sigue entre dos tramos con etiqueta)" if partido else ""
        aviso = (
            f"tramo sin etiqueta propia: la línea {tramo.linea.entity_id} sigue {tramo.largo:.3f} "
            f"en un tramo que ninguna etiqueta toma, unido al suyo; se le suma{mitad} — claro "
            f"{antes:.3f} → {antes + parte:.3f}"
        )
        previo = props.get("tramo_sin_etiqueta")
        props["tramo_sin_etiqueta"] = f"{previo}; {aviso}" if previo else aviso
        d.evidence.notes.append(aviso)


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
    # R152: a face drawn in pieces (shorter than ``min_face_overlap`` of the longest face) — the
    # beam is measured end to end, not on the mean of its faces' ends.
    en_tramos: bool = False
    # R172: its axis drawn halfway between its faces, no tag's: the beam's too, counted once.
    ejes: list[Tramo] = field(default_factory=list)


def _a_lo_largo(origen: Point, u: Point, p: Point) -> tuple[float, float]:
    """A point's place along the axis and across it."""
    dx, dy = p[0] - origen[0], p[1] - origen[1]
    return dx * u[0] + dy * u[1], -dx * u[1] + dy * u[0]


def _vigas(
    grupo: list[_Marcada], config: BeamDetectorConfig, index: SpatialIndex | None = None
) -> list[_Viga]:
    """The beam lines of one kind of tag: its chosen runs, the two faces of one beam merged
    (``_caras_de_una_viga``) — as far apart as the widest definition of their tags' marks plus
    ``face_width_margin``, never less than ``max_face_gap``; with no width declared, up to twice
    that with the beam's axis drawn halfway between them (R172)."""
    tramos: dict[tuple[str, int], Tramo] = {}
    anchos: dict[tuple[str, int], list[float]] = {}
    for m in grupo:
        assert m.elegida is not None
        tramos.setdefault(m.elegida.tramo.clave, m.elegida.tramo)
        if m.ancho is not None:
            anchos.setdefault(m.elegida.tramo.clave, []).append(m.ancho)
    claves = list(tramos)
    padre = {c: c for c in claves}

    def raiz(c: tuple[str, int]) -> tuple[str, int]:
        while padre[c] != c:
            padre[c] = padre[padre[c]]
            c = padre[c]
        return c

    for i, a in enumerate(claves):
        for b in claves[i + 1 :]:
            declarados = anchos.get(a, []) + anchos.get(b, [])
            limite = config.max_face_gap
            if declarados:
                limite = max(limite, max(declarados) + config.face_width_margin)
            if _caras_de_una_viga(tramos[a], tramos[b], config, limite) or (
                not declarados
                and _caras_de_una_viga(tramos[a], tramos[b], config, 2 * limite)
                and _ejes_entre(tramos[a], tramos[b], index, config)
            ):
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
        # Two faces of one beam (much the same length): its axis, the mean of their ends (4.45 and
        # 4.65: 4.55). A face drawn in pieces between openings beside a whole one (R152: the CI of
        # ES-200's 18.15 m wall, the other face in pieces of 5.45, 4.40 and 6.80): end to end — the
        # mean would shorten the beam and leave its end tags outside it.
        en_tramos = any(t.largo < config.min_face_overlap * base.largo for t in caras)
        ejes: dict[tuple[str, int], Tramo] = {}
        for k, cara in enumerate(caras):
            for otra in caras[k + 1 :]:
                for eje in _ejes_entre(cara, otra, index, config):
                    if eje.clave not in claves_caras:
                        ejes.setdefault(eje.clave, eje)
        vigas.append(
            _Viga(
                caras,
                origen,
                u,
                min(inicios) if en_tramos else sum(inicios) / len(inicios),
                max(fines) if en_tramos else sum(fines) / len(fines),
                (min(cruces), max(cruces)),
                sorted(suyas, key=lambda x: (x[0], x[1].indice)),
                en_tramos,
                sorted(ejes.values(), key=lambda t: (_orden_de_id(t.linea.entity_id), t.indice)),
            )
        )
    return vigas


def _caras_de_una_viga(
    a: Tramo, b: Tramo, config: BeamDetectorConfig, limite: float | None = None
) -> bool:
    """Two runs are the faces of one beam when they are drawn on the same layer, parallel, at
    most ``limite`` apart (``max_face_gap`` by default) and overlapping ``min_face_overlap`` of
    the shorter."""
    if a.linea.layer != b.linea.layer:
        return False
    ua, ub = a.direccion, b.direccion
    if abs(ua[0] * ub[0] + ua[1] * ub[1]) < math.cos(_MISMA_DIRECCION * 2):
        return False
    pa, ca = _a_lo_largo(a.p, ua, b.p)
    pb, cb = _a_lo_largo(a.p, ua, b.q)
    tope = config.max_face_gap if limite is None else limite
    if max(abs(ca), abs(cb)) > tope or min(abs(ca), abs(cb)) <= 0.0:
        return False
    return _traslapan(a, b, config)


def _traslapan(a: Tramo, b: Tramo, config: BeamDetectorConfig) -> bool:
    """Two parallel runs overlap ``min_face_overlap`` of the shorter, along ``a``."""
    pa, _ca = _a_lo_largo(a.p, a.direccion, b.p)
    pb, _cb = _a_lo_largo(a.p, a.direccion, b.q)
    traslape = min(a.largo, max(pa, pb)) - max(0.0, min(pa, pb))
    return traslape >= config.min_face_overlap * min(a.largo, b.largo)


def _ejes_entre(
    a: Tramo, b: Tramo, index: SpatialIndex | None, config: BeamDetectorConfig
) -> list[Tramo]:
    """R172: the runs drawn halfway between two parallel faces — on their layer, parallel, within
    ``axis_centre_tolerance`` of their gap from the middle, overlapping both as faces do: the
    beam's axis."""
    if index is None:
        return []
    u = a.direccion
    _pa, ca = _a_lo_largo(a.p, u, b.p)
    _pb, cb = _a_lo_largo(a.p, u, b.q)
    medio, separacion = (ca + cb) / 4, abs(ca + cb) / 2
    if separacion <= 0.0:
        return []
    xs = [a.p[0], a.q[0], b.p[0], b.q[0]]
    ys = [a.p[1], a.q[1], b.p[1], b.q[1]]
    salida: list[Tramo] = []
    for hit in index.entities_in_bbox((min(xs), min(ys), max(xs), max(ys))):
        linea = index.get(hit.entity_id)
        if linea.layer != a.linea.layer or linea.is_closed or not linea.points:
            continue
        if linea.entity_type not in (EntityType.line, EntityType.polyline) or linea.is_annotation:
            continue
        for r in tramos_rectos(linea):
            if r.clave in (a.clave, b.clave):
                continue
            ur = r.direccion
            if abs(u[0] * ur[0] + u[1] * ur[1]) < math.cos(_MISMA_DIRECCION * 2):
                continue
            cruces = [_a_lo_largo(a.p, u, r.p)[1], _a_lo_largo(a.p, u, r.q)[1]]
            tolerancia = config.axis_centre_tolerance * separacion
            if any(abs(c - medio) > tolerancia for c in cruces):
                continue
            if _traslapan(a, r, config) and _traslapan(b, r, config):
                salida.append(r)
    return salida


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
        for t in [*viga.tramos, *viga.ejes]:
            if t.linea.entity_id not in d.source_entities:
                d.source_entities.append(t.linea.entity_id)
        if len(viga.tramos) > 1:
            medida = "de punta a punta (una cara en tramos)" if viga.en_tramos else "su eje"
            con_eje = " y su eje dibujado" if viga.ejes else ""
            aviso_caras = (
                f"claro de una viga dibujada con {len(viga.tramos)} caras ({', '.join(caras)})"
                f"{con_eje}: se mide {medida}, {largo_total:.3f}"
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
            alto = alto_de_texto(m.etiqueta)
            if b - a < _TRAMO_MINIMO * alto:
                # R152: two tags almost at one point of the line (Marina ES-200: two «CI» of a
                # wall drawn across the trabe's line, 0.068 m apart along it) — the cut between
                # them says nothing of either's length.
                dudoso = (
                    f"claro dudoso: su tramo de la línea compartida mide {b - a:.3f}, menos que "
                    f"{_TRAMO_MINIMO:g} alturas de su texto: otra etiqueta está casi en el mismo "
                    "punto de la línea"
                )
                previo = props.get("claro_dudoso")
                props["claro_dudoso"] = f"{previo}; {dudoso}" if previo else dudoso
                d.evidence.notes.append(dudoso)
        _al_maximo(m, output, config)


# R152: a tag's own tramo of a shared line shorter than this many of its text heights is doubtful.
_TRAMO_MINIMO = 2.0


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
    if familia == "dala" and layer_matches(capa, config.concrete_wall_layer_hints):
        # R177: a wall is a dala's own layer for masonry only, never a concrete wall's.
        propias = [h for h in propias if h not in config.wall_layer_hints]
    if propias and layer_matches(capa, propias):
        return 0
    if de_apoyo and layer_matches(capa, de_apoyo):
        return 1
    if layer_matches(capa, config.layer_hints):
        return 2
    return 3


def _sobre_su_muro(etiqueta: NormalizedEntity, familia: str, config: BeamDetectorConfig) -> bool:
    """R169: a dala's tag (CE, CI, DA, DC; or a CR) on a cadenas/dalas layer crowns the wall it
    sits on, whatever its text's direction."""
    return familia in ("dala", "cerramiento") and layer_matches(
        etiqueta.layer, config.dala_tag_layer_hints
    )


def _de_trabe(tramo: Tramo, config: BeamDetectorConfig) -> bool:
    propias = (config.family_layer_hints.get("trabe") or [[]])[0]
    return bool(propias) and layer_matches(tramo.linea.layer, propias)


def _del_muro(
    etiqueta: NormalizedEntity,
    alineadas: list[_Candidata],
    sobre: list[_Candidata],
    config: BeamDetectorConfig,
) -> list[_Candidata]:
    """R169: the runs a dala's tag on its layer may take — its family's own lines and the wall it
    sits on, never a wall's end (a run no longer than ``max_face_gap``: Marina «DC» AF072, in a
    door between two walls, took the 0.3 m end of one). The wall's run its letters sit on (within
    one text height, reaching its span), in any direction, before any aligned one (Marina ES-200:
    «CI» written across a short wall took the trabe's line or the wall's end)."""

    def suyo(c: _Candidata) -> bool:
        if c.preferencia > 1:
            return False
        return c.tramo.largo > config.max_face_gap or not layer_matches(
            c.tramo.linea.layer, config.wall_layer_hints
        )

    alto = alto_de_texto(etiqueta)
    debajo = [c for c in sobre if suyo(c) and c.distancia <= alto]
    return debajo if debajo else [c for c in alineadas if suyo(c)]


def _alineadas(
    etiqueta: NormalizedEntity,
    familia: str,
    tramos: list[Tramo],
    formas: Formas,
    config: BeamDetectorConfig,
    cualquier_direccion: bool = False,
) -> list[_Candidata]:
    """The runs of one line that a tag may dimension: aligned with it (any direction with
    ``cualquier_direccion``), of a beam's length (any length on the family's own layers or the
    wall it sits on), within the search radius of its letters, and running alongside it."""
    giro = math.radians(etiqueta.rotation or 0.0)
    sentido = (math.cos(giro), math.sin(giro))
    alto = alto_de_texto(etiqueta)
    esquinas = esquinas_de_texto(etiqueta)
    letras = formas.de(etiqueta)
    salida: list[_Candidata] = []
    for tramo in tramos:
        ux, uy = tramo.direccion
        coseno = min(1.0, abs(ux * sentido[0] + uy * sentido[1]))
        if math.degrees(math.acos(coseno)) > config.alignment_tolerance_deg and not (
            cualquier_direccion
        ):
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
