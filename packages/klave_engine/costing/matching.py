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
    "herramienta equipo desperdicios acarreos limpieza pu p.u "
    # El verbo con el que abre casi todo renglón publicado: dice qué se hace,
    # nunca qué es. "Suministro y colocación de tubo conduit" y "Canalización
    # con tubo conduit" son el mismo concepto y no comparten el verbo.
    "fabricacion fabricación habilitado tendido montaje instalacion instalación "
    "aplicado prueba pruebas".split()
)
FAMILY_WORDS = (
    "muro", "castillo", "columna", "trabe", "contratrabe", "losa", "zapata", "dala",
    "cerramiento", "pilote", "cimbra", "acero", "concreto", "firme", "plafon", "plafón",
    "aplanado", "pintura", "piso", "despalme", "corte", "terraplen", "terraplén",
    "excavacion", "excavación", "relleno", "plantilla", "trazo", "nivelacion", "nivelación",
    "malla", "vigueta", "bovedilla", "block", "tabique", "ladrillo",
    # Instalaciones y cancelería: sin estas palabras _head() no encontraba
    # familia en ningún renglón de instalaciones, y la señal de familia —
    # que es la que separa una tubería de una salida — se perdía entera.
    "tuberia", "tubería", "tubo", "salida", "ducto", "conduit", "canalizacion",
    "canalización", "ramaleo", "ramal", "albañal", "albanal", "bajada", "registro",
    "coladera", "valvula", "válvula", "mueble", "lavabo", "regadera", "inodoro",
    "cancel", "canceleria", "cancelería", "ventana", "puerta", "contacto",
    "apagador", "luminaria", "tablero", "rejilla", "difusor", "alimentador",
    # Trabajos auxiliares que se nombran POR la cosa que preparan: una
    # «ranura para alojar tubería» no es tubería, y un «sondeo de ducto» no es
    # ducto. Sin estas palabras _head() se quedaba con el objeto de la frase
    # en lugar de su sujeto, y el preparativo ganaba sobre el concepto.
    "ranura", "ranurado", "sondeo", "cajillo", "chambrana", "resane", "recorte",
    "perforacion", "perforación", "apertura", "cala",
)

# Cómo se dice lo mismo en el catálogo de un taller y en un tabulador
# publicado. No son sinónimos del idioma: son sinónimos del oficio, y sin
# ellos «canalización» y «tubo conduit» no se parecen en nada.
SINONIMOS: dict[str, str] = {
    "canalizacion": "conduit",
    "poliducto": "conduit",
    "ramaleo": "tuberia",
    "ramal": "tuberia",
    "tubo": "tuberia",
    "albanal": "sanitaria",
    "drenaje": "sanitaria",
    "inodoro": "wc",
    "excusado": "wc",
    "taza": "wc",
    "canceleria": "cancel",
    "tomacorriente": "contacto",
    "interruptor": "apagador",
    "lampara": "luminaria",
    "alumbrado": "luminaria",
    "preparacion": "salida",
}
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


# La partida a la que pertenece un renglón, en un vocabulario común para el
# catálogo del taller y para un tabulador publicado. Es la señal más barata y
# más fuerte que hay: un renglón de instalación eléctrica no puede ser el
# precio de una tubería de gas por mucho que las dos digan «tubo».
_PARTIDA_POR_PREFIJO: dict[str, str] = {
    "PRE": "preliminares", "TER": "terracerias", "CIM": "cimentacion",
    "EST": "estructura", "ALB": "albanileria", "ACB": "acabados", "ACA": "acabados",
    "INE": "electrica", "INS": "sanitaria", "INH": "hidraulica", "ING": "gas",
    "INA": "aire", "AIR": "aire", "CAN": "canceleria", "CAR": "canceleria",
    "HID": "hidraulica", "SAN": "sanitaria", "ELE": "electrica", "GAS": "gas",
}
_PARTIDA_POR_TEXTO: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("electrica", re.compile(r"el[eé]ctric|conduit|poliducto|luminaria|apagador|"
                             r"contacto|tablero|centro de carga|cable|alambre", re.I)),
    ("hidraulica", re.compile(r"hidr[aá]ulic|agua fr[ií]a|agua caliente|cpvc|ppr|"
                              r"polipropileno|tinaco|cisterna|bomba", re.I)),
    ("sanitaria", re.compile(r"sanitari|alba[ñn]al|drenaje|pluvial|registro|coladera|"
                             r"bajada de agua", re.I)),
    ("gas", re.compile(r"gas|pead", re.I)),
    ("aire", re.compile(r"aire acondicionado|ducto|difusor|rejilla|minisplit|"
                        r"refrigerant", re.I)),
    ("canceleria", re.compile(r"cancel|ventana|puerta|vidrio|cristal|alumini", re.I)),
    ("terracerias", re.compile(r"despalme|terrapl[eé]n|corte en terreno", re.I)),
    ("cimentacion", re.compile(r"cimentaci|zapata|pilote|contratrabe|plantilla", re.I)),
    ("estructura", re.compile(r"columna|castillo|trabe|losa|acero de refuerzo|cimbra", re.I)),
    ("acabados", re.compile(r"pintura|plafon|piso|loseta|azulejo|aplanado", re.I)),
    ("albanileria", re.compile(r"muro|tabique|block|firme|repellado", re.I)),
)


def partida_por_texto(description: str, declared: str = "") -> str:
    """La partida según lo que el renglón dice ser. Vacío si no lo dice."""
    material = f"{declared} {description}"
    for partida, patron in _PARTIDA_POR_TEXTO:
        if patron.search(material):
            return partida
    return ""


def partida_de(clave: str, description: str = "", declared: str = "") -> str:
    """La partida canónica de un renglón: primero por lo que dice ser, y sólo
    si se calla, por el prefijo de su clave.

    El orden importa y costó descubrirlo: el prefijo dice dónde lo archivó
    alguien, no qué es. Un taller archiva «ramaleo a base de tubería de
    polipropileno» bajo ALB —albañilería— porque ranurar el muro es trabajo de
    albañil, y eso no lo vuelve albañilería a la hora de buscarle precio a una
    tubería. Cadena vacía cuando no se puede saber, que es distinto de saber
    que no coincide."""
    por_texto = partida_por_texto(description, declared)
    if por_texto:
        return por_texto
    for texto in (declared, clave):
        for parte in re.split(r"[^A-Za-z]+", (texto or "").upper()):
            if parte in _PARTIDA_POR_PREFIJO:
                return _PARTIDA_POR_PREFIJO[parte]
    return ""


# En un catálogo mexicano el renglón se escribe «<concepto>, incluye:
# <alcances>». Lo de antes dice qué es; lo de después dice hasta dónde llega
# el precio. Mezclarlos hace que «cople, etiqueta verde» pesen tanto como
# «tubo conduit», y entonces dos renglones del mismo concepto con alcances
# distintos dejan de parecerse.
_ALCANCE = re.compile(r"\b(incluye|incluyendo|inc\.)\b\s*:?\s*", re.IGNORECASE)


def split_alcance(text: str) -> tuple[str, str]:
    """La identidad del concepto y su alcance, por separado."""
    partes = _ALCANCE.split(text or "", maxsplit=1)
    if len(partes) < 3:
        return (text or "").strip(" ,.;"), ""
    return partes[0].strip(" ,.;"), partes[2].strip(" ,.;")


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
        out.add(SINONIMOS.get(w, w))
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


def _familia_canonica(word: str) -> str:
    """La familia bajo su nombre canónico: «ramaleo» y «tubo» son «tubería».

    Los sinónimos tienen que aplicarse aquí igual que en los tokens. Cuando
    sólo se aplicaban a los tokens, «ramaleo a base de tubería» contaba como
    otra familia que «tubería», se llevaba el castigo de cabeza distinta y el
    renglón correcto desaparecía de los candidatos."""
    canonica = normalize(word)
    return SINONIMOS.get(canonica, canonica)


def _head(text: str) -> str | None:
    """The first family word in a description: what the concept IS
    ("aplanado … en muros" is an aplanado, "muro … con aplanado" a muro)."""
    low = normalize(text)
    best: tuple[int, str] | None = None
    for word in FAMILY_WORDS:
        position = low.find(normalize(word))
        if position >= 0 and (best is None or position < best[0]):
            best = (position, _familia_canonica(word))
    return best[1] if best else None


class _Profile:
    """A description analysed once: tokens, specs, head, negatives.

    ``tokens`` son las de la identidad — lo que el concepto ES — y ``alcance``
    las de lo que el precio incluye. Se guardan aparte porque pesan distinto:
    dos renglones del mismo concepto pueden traer alcances muy diferentes y
    siguen siendo el mismo concepto."""

    __slots__ = ("tokens", "alcance", "specs", "head", "negative", "families")

    def __init__(self, text: str) -> None:
        identidad, alcance = split_alcance(text)
        low = normalize(text)
        self.tokens = tokens(identidad)
        self.alcance = tokens(alcance)
        self.specs = _specs(identidad)
        self.head = _head(identidad)
        self.negative = any(normalize(w) in low for w in NEGATIVE_WORDS)
        self.families = {
            _familia_canonica(w) for w in FAMILY_WORDS if normalize(w) in normalize(identidad)
        }


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
    # El alcance suma poco a propósito: que los dos digan «incluye acarreos»
    # confirma un poco, y que no lo digan no los vuelve conceptos distintos.
    if ours.alcance and theirs.alcance:
        alcance_comun = ours.alcance & theirs.alcance
        if alcance_comun:
            value += 0.06 * min(len(alcance_comun) / len(ours.alcance), 1.0)
            reasons.append("alcance parecido: " + ", ".join(sorted(alcance_comun)[:3]))
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
    nuestra = partida_de("", description, phase)
    suya = partida_de(candidate.clave, candidate.description, candidate.phase)
    # El castigo se apoya sólo en lo que el renglón dice ser. Dónde lo archivó
    # su catálogo puede sugerir, nunca descartar.
    suya_dicha = partida_por_texto(candidate.description, candidate.phase)
    # La partida es la señal más gruesa que hay, así que sólo habla cuando las
    # finas se callan. Si las familias ya coincidieron, decir además que están
    # en la misma partida no agrega información — la repite más gruesa — y
    # sumar por eso aplasta la diferencia entre un firme de 10 cm y uno de 8.
    # Si algo ya dijo que son cosas distintas, tampoco hay qué corroborar.
    ya_hablaron = bool(
        (ours.families & theirs.families)
        or (ours.head and theirs.head and ours.head != theirs.head)
        or (theirs.negative and not ours.negative)
    )
    if nuestra and suya:
        if nuestra == suya:
            if not ya_hablaron:
                value += 0.10
                reasons.append(f"misma partida: {nuestra}")
        elif suya_dicha and suya_dicha != nuestra:
            # No es un matiz: un renglón de otra partida es otro concepto.
            # Sin este castigo «alimentación eléctrica … con tubo» ganaba
            # sobre una tubería de gas por compartir la palabra tubo.
            value -= 0.25
            reasons.append(f"otra partida: {suya_dicha}, no {nuestra}")
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
