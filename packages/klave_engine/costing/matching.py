"""Match the engine's concepts to the taller's own catálogo.

The estimator's translation work: "muro de block" in Klave is MUR-015 in
their book, at their price, with their description. This ranks candidate
rows (reference prices from the taller's catálogo or a tabulador, and the
workspace's own concepts) against a concept and explains every score, so
the match is adoptable at a glance and auditable afterwards:

- the unit must agree (M2 never matches M3);
- shared words between the descriptions, after stopwords, weigh most;
- numbers agree or disagree loudly (f'c=250 vs 200, 15x20 vs 20x20, 12 cm
  vs 10 cm) — a spec mismatch is a different concept, not a near miss;
- the partida (cimentación, estructura…) and the family word (muro, trabe,
  losa, castillo…) add a little.

Scores live in [0, 1]; 0.8 and above is "the same thing said differently".
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

STOPWORDS = frozenset(
    "de del la el los las y o en con por para a al un una incluye incluyendo inc tipo "
    "segun según hasta desde sobre entre sin su sus se que como mas más cm m kg pza ton "
    "lt m2 m3 ml kg/cm2 kg/cm² acabado suministro colocacion colocación aplicacion "
    "aplicación todo lo necesario para su correcta ejecucion ejecución materiales mano obra "
    "herramienta equipo desperdicios acarreos limpieza pu p.u".split()
)
FAMILY_WORDS = (
    "muro", "castillo", "columna", "trabe", "contratrabe", "losa", "zapata", "dala",
    "cerramiento", "pilote", "cimbra", "acero", "concreto", "firme", "plafon", "plafón",
    "aplanado", "pintura", "piso", "despalme", "corte", "terraplen", "terraplén",
    "excavacion", "excavación", "relleno", "plantilla", "trazo", "nivelacion", "nivelación",
    "malla", "vigueta", "bovedilla", "block", "tabique", "ladrillo",
)
# A candidate that is the undoing, removal or mere supply of the thing is
# not the thing: "demolición de losa" never matches "losa".
NEGATIVE_WORDS = (
    "demolicion", "demolición", "retiro", "desmantel", "desmontaje", "reparacion",
    "reparación", "renta", "flete", "acarreo de escombro", "limpieza de",
)
_CM_RE = re.compile(r"\b(\d{1,3}(?:[.,]\d)?)\s*(?:cms?\.?|cent[ií]metros?)\b", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
_DIM_RE = re.compile(r"\b(\d{1,3})\s*[x×]\s*(\d{1,3})(?:\s*[x×]\s*(\d{1,3}))?\b", re.IGNORECASE)
_FC_RE = re.compile(r"f['’]?c\s*=?\s*(\d{2,3})", re.IGNORECASE)


@dataclass
class Candidate:
    kind: str  # reference | concept
    key: str  # ref_id as text, or the concept code
    clave: str
    description: str
    unit: str
    price: float | None
    source: str = ""
    vigencia: str = ""
    phase: str = ""


@dataclass
class Match:
    candidate: Candidate
    score: float
    reasons: list[str] = field(default_factory=list)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.lower().replace("/", " ").replace("-", " ").split())


def tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9.]+", normalize(text))
    out: set[str] = set()
    for w in words:
        w = w.strip(".")
        if len(w) < 3 or w in STOPWORDS or w.replace(".", "").isdigit():
            continue
        # crude stemming: plurals and gendered endings collapse
        if len(w) > 5 and w.endswith(("es", "os", "as")):
            w = w[:-2]
        elif len(w) > 4 and w.endswith("s"):
            w = w[:-1]
        out.add(w)
    return out


def unit_key(unit: str) -> str:
    u = normalize(unit).replace(" ", "").replace("²", "2").replace("³", "3").upper()
    return {"ML": "M", "MT": "M", "MTS": "M", "M.L.": "M", "M2.": "M2", "PZA.": "PZA",
            "PIEZA": "PZA", "PZAS": "PZA", "JOR": "JOR", "SAL": "SAL", "LOTE": "LOTE",
            "KG.": "KG"}.get(u, u)


def _specs(text: str) -> dict[str, set[str]]:
    low = normalize(text)
    fc = {m.group(1) for m in _FC_RE.finditer(low)}
    dims = {
        "x".join(g for g in m.groups() if g) for m in _DIM_RE.finditer(low)
    }
    cm = {m.group(1).replace(",", ".") for m in _CM_RE.finditer(low)}
    plain = {n.replace(",", ".") for n in _NUMBER_RE.findall(low)}
    plain -= fc
    plain -= cm
    for d in dims:
        plain -= set(d.split("x"))
    return {"fc": fc, "dims": dims, "cm": cm, "numbers": plain}


def _head(text: str) -> str | None:
    """The first family word in a description: what the concept IS
    ("aplanado … en muros" is an aplanado, "muro … con aplanado" a muro)."""
    low = normalize(text)
    best: tuple[int, str] | None = None
    for word in FAMILY_WORDS:
        position = low.find(normalize(word))
        if position >= 0 and (best is None or position < best[0]):
            best = (position, normalize(word))
    return best[1] if best else None


class _Profile:
    """A description analysed once: tokens, specs, head, negatives."""

    __slots__ = ("tokens", "specs", "head", "negative", "families")

    def __init__(self, text: str) -> None:
        low = normalize(text)
        self.tokens = tokens(text)
        self.specs = _specs(text)
        self.head = _head(text)
        self.negative = any(normalize(w) in low for w in NEGATIVE_WORDS)
        self.families = {normalize(w) for w in FAMILY_WORDS if normalize(w) in low}


_PROFILES: dict[str, _Profile] = {}


def profile(text: str) -> _Profile:
    cached = _PROFILES.get(text)
    if cached is None:
        if len(_PROFILES) > 20000:
            _PROFILES.clear()
        cached = _PROFILES[text] = _Profile(text)
    return cached


def score(
    description: str, unit: str, candidate: Candidate, phase: str = ""
) -> Match | None:
    """None when the units cannot agree; else the match with its reasons."""
    if unit_key(unit) != unit_key(candidate.unit):
        return None
    ours, theirs = profile(description), profile(candidate.description)
    a, b = ours.tokens, theirs.tokens
    if not a or not b:
        return None
    reasons: list[str] = []
    shared = a & b
    jaccard = len(shared) / len(a | b)
    coverage = len(shared) / len(a)  # how much of OUR description the candidate repeats
    value = 0.55 * coverage + 0.25 * jaccard
    if shared:
        reasons.append("palabras en común: " + ", ".join(sorted(shared)[:6]))
    if theirs.negative and not ours.negative:
        value -= 0.5
        reasons.append("es demolición/retiro/renta, no el concepto")
    if ours.families and theirs.families:
        if ours.head and theirs.head and ours.head != theirs.head:
            value -= 0.3
            reasons.append(f"es un(a) {theirs.head}, no un(a) {ours.head}")
        elif ours.families & theirs.families:
            value += 0.12
            shared_families = sorted(ours.families & theirs.families)[:3]
            reasons.append("misma familia: " + ", ".join(shared_families))
        else:
            value -= 0.35
            reasons.append(
                f"otra familia: {', '.join(sorted(theirs.families)[:2])} vs "
                f"{', '.join(sorted(ours.families)[:2])}"
            )
    sa, sb = ours.specs, theirs.specs
    if sa["fc"] and sb["fc"]:
        if sa["fc"] & sb["fc"]:
            value += 0.08
            reasons.append(f"f'c={next(iter(sa['fc'] & sb['fc']))} coincide")
        else:
            value -= 0.3
            reasons.append(f"f'c distinto ({', '.join(sb['fc'])} vs {', '.join(sa['fc'])})")
    if sa["dims"] and sb["dims"]:
        if sa["dims"] & sb["dims"]:
            value += 0.08
            reasons.append(f"sección {next(iter(sa['dims'] & sb['dims']))} coincide")
        else:
            value -= 0.2
            reasons.append(f"sección distinta ({', '.join(sorted(sb['dims']))})")
    if sa["cm"] and sb["cm"]:
        if sa["cm"] & sb["cm"]:
            value += 0.06
            reasons.append(f"{next(iter(sa['cm'] & sb['cm']))} cm coincide")
        else:
            value -= 0.2
            reasons.append(f"espesor distinto ({', '.join(sorted(sb['cm']))} cm)")
    if sa["numbers"] and sb["numbers"]:
        if sa["numbers"] & sb["numbers"]:
            value += 0.04
        elif not (sa["fc"] & sb["fc"] or sa["dims"] & sb["dims"] or sa["cm"] & sb["cm"]):
            value -= 0.05
    if phase and candidate.phase:
        pa, pb = normalize(phase), normalize(candidate.phase)
        if pa in pb or pb in pa:
            value += 0.05
            reasons.append("misma partida")
    value = max(0.0, min(1.0, value))
    if value < 0.15:
        return None
    return Match(candidate=candidate, score=round(value, 3), reasons=reasons)


def rank(
    description: str, unit: str, candidates: list[Candidate], *, phase: str = "", limit: int = 8
) -> list[Match]:
    matches = [m for m in (score(description, unit, c, phase) for c in candidates) if m]
    matches.sort(key=lambda m: (-m.score, m.candidate.clave))
    return matches[:limit]
