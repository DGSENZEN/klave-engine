"""Hallazgos: what is wrong with this presupuesto, ranked by what it costs.

A presupuesto today can carry forty warnings that all look the same. Some
mean the deliverable is invalid, some mean the total is short by an unknown
amount, and some are the engine explaining a deliberate choice. Shown as one
flat list they are read as noise and none of them get acted on — the failure
that alarm engineering calls *alarm fatigue*.

So every finding is rationalized before it is shown, the way an alarm
philosophy rationalizes an alarm: it must name a consequence, carry the
money or the quantity that consequence puts at stake, and say what to do
about it. A finding that cannot say those three things is a note, not an
alarm.

**Three** actionable tiers, ordered by consequence — and a fourth channel
that is deliberately not an alarm:

``bloqueante``  Entregarlo así estaría mal. The total is not a price (no
                reliable units), or the presupuesto contradicts the plano
                it claims to read. Exporting over one of these takes a
                written reason, and the reason travels inside the file.
``dinero``      There is a real quantity whose money is missing or unknown:
                the total is understated and the amount is not knowable
                from here. Never guessed — the physical exposure is shown
                instead (23 PZA, 108.5 m²).
``revisar``     A human decision is pending; the number is defensible
                without it (vigencias, cobertura, lecturas de baja
                confianza).

``criterios``   A deliberate engine choice worth recording — and by the
                standard's own test, *not an alarm*: nothing is required of
                the reader. It leaves the feed and joins the assumptions
                register, where it does the job it is actually good for
                (defending the number later) instead of diluting the three
                tiers above it.

Every finding also carries its **last responsible moment** (``momento``):
the stage after which fixing it stops being cheap. That is the estimating
analogue of an alarm's time-to-respond, and it is what lets someone triage
a list without reading all of it.

Nothing is ever swallowed: a warning this module does not recognize still
appears, at ``revisar``, with its original text.
"""

from __future__ import annotations

import hashlib
import re
from typing import Literal

from pydantic import BaseModel, Field

from klave_engine.costing.models import CostReport
from klave_engine.costing.reviews import ProjectReviews

Severity = Literal["bloqueante", "dinero", "revisar"]
SEVERITY_ORDER: dict[str, int] = {"bloqueante": 0, "dinero": 1, "revisar": 2}

# When fixing this stops being cheap. Ordered from most to least urgent.
Momento = Literal["entregar", "cotizar", "contratar", "sin_urgencia"]
MOMENTO_LABEL: dict[str, str] = {
    "entregar": "antes de entregar",
    "cotizar": "antes de cotizar",
    "contratar": "antes de contratar",
    "sin_urgencia": "sin urgencia",
}


class Hallazgo(BaseModel):
    """One rationalized finding: consequence, stake, and the way out."""

    id: str
    severity: Severity
    # One line an engineer can act on without opening anything else.
    title: str
    detail: str = ""
    # The imperative: what this person does next.
    action: str = ""
    # Where that is done, as an app route relative to the project.
    target: str | None = None
    # How to confirm the finding is real, in the drawing's own terms (hoja,
    # capa, marcas). A warning the reader cannot check is a warning they
    # eventually stop believing.
    verificar: str = ""
    # The last responsible moment: after this, fixing it costs money or a
    # change order instead of effort.
    momento: Momento = "entregar"
    # Pesos this finding puts in question — money already in the total that
    # depends on the finding being resolved the way the engine assumed.
    monto_afectado: float | None = None
    # What is at stake when the money is genuinely unknowable ("23 PZA").
    # Never a peso figure the engine cannot derive: an invented exposure is
    # worse than an honest "no se sabe".
    exposicion: str | None = None
    concept_code: str | None = None


class Diagnostico(BaseModel):
    """The page's honest headline plus every finding behind it."""

    hallazgos: list[Hallazgo] = Field(default_factory=list)
    # Deliberate engine choices: not alarms (nothing is asked of the reader),
    # but exactly what defends the number under scrutiny months later.
    criterios: list[str] = Field(default_factory=list)
    by_severity: dict[str, int] = Field(default_factory=dict)
    # Money already counted that some finding calls into question.
    monto_en_duda: float = 0.0
    # Conceptos with a real quantity and no price: the total omits them.
    conceptos_sin_precio: int = 0
    # True when the presupuesto may be handed to a client as it stands.
    entregable: bool = True
    # One sentence stating what this presupuesto is, honestly.
    resumen: str = ""

    @property
    def bloqueantes(self) -> list[Hallazgo]:
        return [h for h in self.hallazgos if h.severity == "bloqueante"]


# --------------------------------------------------------------- patterns


class Rule(BaseModel):
    """How one family of engine prose becomes a finding.

    ``severity=None`` drops the text because a structural finding already
    says the same thing with numbers attached — never because it is
    inconvenient. ``plural`` is the headline used when the family repeats:
    six copies of one problem are one problem, and showing them six times is
    the flood that teaches people to ignore the list."""

    pattern: str
    severity: Severity | None
    action: str = ""
    target: str | None = None
    group: str = ""
    plural: str = ""  # "{n}" is replaced by the count
    momento: Momento = "entregar"
    verificar: str = ""
    # True for prose that is a recorded criterion, not something to act on.
    criterio: bool = False


_RULES: list[Rule] = [
    Rule(
        pattern=r"SIN UNIDADES",
        severity=None,  # said structurally, with the verification route attached
    ),
    Rule(
        pattern=r"sin matriz ni precio adoptado|sin costo hasta que el catálogo",
        severity=None,  # said structurally from BoqLine.unpriced
    ),
    Rule(
        pattern=r"El plano declara f'?c=(\d+).*el concepto costea f'?c=(\d+)",
        severity="bloqueante",
        action="Ajusta esos conceptos o sus matrices al f'c que declara el plano.",
        target="parametros",
        group="fc_menor_al_plano",
        plural="{n} conceptos costean un f'c menor al que declara el plano",
        momento="cotizar",
        verificar="Contrasta las notas de f'c del plano con la matriz de cada concepto.",
    ),
    Rule(
        pattern=r"acero no cuantificado|sin armado en su etiqueta|ese acero no se cuantificó",
        severity="dinero",
        action="Captura el armado del detalle o del cuadro para que el acero entre al costo.",
        target="lectura",
        group="acero_sin_cuantificar",
        plural="{n} elementos sin armado leído: ese acero no está costeado",
        momento="cotizar",
        verificar="Busca el armado en el cuadro o el detalle de esos elementos.",
    ),
    Rule(
        pattern=r"tienen un P\.U\. de destajo",
        severity="dinero",
        action="Cárgales el material, o adopta un precio unitario que lo incluya.",
        target="/catalogo",
        momento="cotizar",
        verificar=(
            "Un catálogo de destajos paga la mano de obra y nada más. En una "
            "línea sanitaria de 4 pulgadas el tubo cuesta cinco veces el destajo, "
            "y el presupuesto está sumando sólo el destajo."
        ),
    ),
    Rule(
        pattern=r"La plantilla de personal de campo suma",
        severity="dinero",
        action=(
            "Ajusta el porcentaje de indirectos de campo, o la plantilla, "
            "para que uno pague a la otra."
        ),
        target="programa",
        momento="cotizar",
        verificar=(
            "Compara el total de la plantilla contra los indirectos de campo: "
            "ese personal se paga con o sin formato de por medio, y en obra "
            "pública además se revisa (RLOPSRM art. 64-A-I)."
        ),
    ),
    Rule(
        pattern=r"locales sin clave de acabado",
        severity="revisar",
        action="Marca el piso y el plafón de esos locales en el plano de acabados.",
        target="lectura",
        group="locales_sin_acabado",
        plural="{n} hojas con locales sin clave de acabado",
        momento="cotizar",
        verificar=(
            "El local sin marca no declara acabado: su área existe pero no "
            "pertenece a ningún concepto todavía."
        ),
    ),
    Rule(
        pattern=r"piezas? de cancelería sin clave",
        severity="revisar",
        action="Revisa los globos de nomenclatura sin atributo de clave en el plano.",
        target="lectura",
        group="canceleria_sin_clave",
        plural="{n} hojas con piezas de cancelería sin clave legible",
        momento="cotizar",
        verificar=(
            "El globo sin clave no declara qué pieza es: no puede entrar al "
            "cuadro ni al presupuesto. Sigue contado en el levantamiento."
        ),
    ),
    Rule(
        pattern=r"corridas de instalación sin diámetro legible",
        severity="dinero",
        action="Rotula el diámetro sobre el trazo, o decláralo al adoptar el precio.",
        target="lectura",
        group="corridas_sin_diametro",
        plural="{n} hojas con corridas sin diámetro legible",
        momento="cotizar",
        verificar=(
            "Nadie publica precio de «tubería» a secas: sin diámetro, esos "
            "metros no se pueden cotizar contra ninguna publicación."
        ),
    ),
    Rule(
        pattern=r"tiros de bajada ligados sin niveles",
        severity="revisar",
        action="Declara los N.P.T. de cada planta para medir el tramo vertical.",
        target="lectura",
        group="bajadas_sin_nivel",
        plural="{n} hojas con tiros de bajada sin nivel de dónde medirse",
        momento="entregar",
        verificar=(
            "El tiro está ligado por posición entre plantas; lo que falta es "
            "el nivel que convierte los niveles en metros verticales."
        ),
    ),
    Rule(
        pattern=r"nivel de plataforma",
        severity="revisar",
        action="Define el nivel de plataforma en Parámetros para calcular corte y terraplén.",
        target="parametros",
        momento="cotizar",
        verificar="El plano trae curvas de nivel; falta el nivel de proyecto.",
    ),
    Rule(
        pattern=r"sin cantidades: no hubo detecciones aplicables",
        severity="revisar",
        action="Revisa si ese concepto aplica a esta obra.",
        target="revision",
        group="concepto_sin_cantidad",
        plural="{n} conceptos del catálogo se quedaron sin cantidad",
    ),
    Rule(
        pattern=r"Oficina central por share fijado: ",
        severity="revisar",
        criterio=True,
    ),
    Rule(
        pattern=r"vigencia|vencido|por revisar",
        severity="revisar",
        action="Actualiza o cotiza esos precios en el catálogo.",
        target="/catalogo",
        momento="cotizar",
        verificar="Revisa la vigencia de cada insumo en el catálogo.",
    ),
    Rule(
        pattern=r"sin cimbra de contacto|el apuntalamiento va en la matriz",
        severity=None,
        criterio=True,
    ),
    Rule(
        pattern=r"deduplican|segmentado en|Altura total del edificio",
        severity=None,
        criterio=True,
    ),
    Rule(
        pattern=r"Integración \((CI-C|CI-O|FI|CA)\): ",
        severity="revisar",
        action="Completa la captura para que el análisis sustituya al porcentaje declarado.",
        target="parametros",
        group="integracion_incompleta",
        plural="{n} componentes de la integración siguen por porcentaje declarado",
        momento="cotizar",
        verificar="Revisa Integración en parámetros del proyecto y en el catálogo del taller.",
    ),
    Rule(
        pattern=r"Utilidad declarada: ",
        severity="revisar",
        criterio=True,
    ),
    Rule(
        pattern=r"costo de financiamiento no convergió",
        severity="dinero",
        action="Revisa tasa y calendario del flujo; el residual indica cuánto baila el total.",
        target="parametros",
        momento="entregar",
        verificar="Compara el total de dos recomputos seguidos.",
    ),
]

_FALLBACK = Rule(pattern="", severity="revisar")

# Sentences the engine appends telling the reader what to do: they belong in
# the finding's action, not repeated inside its title.
_ACTION_SENTENCE = re.compile(
    r"(?:^|\s)(Ajusta|Captura|Define|Revisa|Actualiza|Confirma|Corrige|Da)\b[^.]*\.?\s*$",
    re.IGNORECASE,
)


def promote_detection_warnings(warnings: list[str]) -> list[str]:
    """Los avisos de detección que el diagnóstico sabe clasificar.

    El detector conoce denominadores que el presupuesto no ve (piezas sin
    clave, por ejemplo). Viaja al diagnóstico solo lo que una regla con
    severidad reconoce; el ruido de detección genérico se queda donde
    estaba — promover todo sería inundar la lista que este módulo existe
    para no inundar."""
    promoted: list[str] = []
    for text in warnings:
        for rule in _RULES:
            if rule.severity is not None and re.search(rule.pattern, text, re.I):
                promoted.append(text)
                break
    return promoted


def _classify(text: str) -> Rule:
    for rule in _RULES:
        if re.search(rule.pattern, text, re.IGNORECASE):
            return rule
    # Unknown warnings are never swallowed; they are simply not promoted.
    return _FALLBACK


def _headline(text: str, limit: int = 120) -> str:
    """The warning as a title: its own instruction stripped (the finding
    carries one), trimmed to something a person reads in one pass."""
    stripped = _ACTION_SENTENCE.sub("", text).strip().rstrip(".;,").strip()
    stripped = stripped or text
    return stripped if len(stripped) <= limit else stripped[: limit - 1] + "…"


def _stable_id(text: str) -> str:
    """Same warning, same id across restarts: the UI keys rows on this."""
    return hashlib.blake2s(text.encode("utf-8"), digest_size=4).hexdigest()


_CONCEPT_RE = re.compile(r"\b([A-Z]{2,4}-\d{3})\b")


def _concept_in(text: str) -> str | None:
    match = _CONCEPT_RE.search(text)
    return match.group(1) if match else None


def _money(value: float) -> str:
    return f"${value:,.0f}"


# ------------------------------------------------------------ diagnosing


def diagnose(
    report: CostReport,
    reviews: ProjectReviews | None = None,
    cobertura: list[dict] | None = None,
) -> Diagnostico:
    """Every finding this presupuesto carries, rationalized and ranked.

    Structural checks come first because they can carry real numbers; the
    engine's remaining prose warnings are classified and appended."""
    hallazgos: list[Hallazgo] = []
    boq = report.boq
    by_code = {line.concept_code: line for line in boq.lines}

    # --- bloqueante: the total is not a price at all -------------------
    if not boq.units_reliable:
        hallazgos.append(
            Hallazgo(
                id="unidades_no_confiables",
                severity="bloqueante",
                title="El plano no declara una unidad confiable",
                detail=(
                    "Las cantidades están en unidades de dibujo y ninguna línea lleva "
                    "precio: este total no es un precio. Confirmar la unidad recalcula "
                    "todo el presupuesto."
                ),
                action="Confirma la unidad del plano en el Resumen.",
                target="",
                verificar="Compara una cota conocida del plano contra la medida del visor.",
                momento="entregar",
            )
        )

    # --- dinero: real quantity, unknown money --------------------------
    unpriced = [line for line in boq.lines if line.unpriced]
    for line in unpriced:
        hallazgos.append(
            Hallazgo(
                id=f"sin_precio:{line.concept_code}",
                severity="dinero",
                title=f"{line.concept_code} tiene cantidad pero no precio",
                detail=(
                    f"{line.description[:80]} — {line.quantity:,.2f} {line.unit} "
                    "cuantificados que el costo directo no incluye. Cuánto suman no se "
                    "puede saber desde aquí: depende del precio que le des."
                ),
                action=f"Dale precio a {line.concept_code} en el catálogo del taller.",
                target="/catalogo",
                exposicion=f"{line.quantity:,.2f} {line.unit}",
                concept_code=line.concept_code,
                verificar=f"Revisa la línea {line.concept_code} en el presupuesto.",
                momento="cotizar",
            )
        )

    # --- revisar: the verification gate --------------------------------
    if reviews is not None:
        pending = [
            label
            for label, done in (
                ("unidades", reviews.verification.units_confirmed_at is not None),
                ("detecciones", reviews.verification.detections_confirmed_at is not None),
                ("supuestos", reviews.verification.assumptions_confirmed_at is not None),
            )
            if not done
        ]
        if pending:
            hallazgos.append(
                Hallazgo(
                    id="verificacion_pendiente",
                    severity="revisar",
                    title=f"Faltan {len(pending)} de 3 pasos de verificación",
                    detail=(
                        "Sin firmar " + ", ".join(pending) + ". Hasta entonces las "
                        "pantallas y el Excel salen sellados SIN VERIFICAR: el "
                        "presupuesto es tuyo cuando tú lo confirmas, no cuando el "
                        "motor lo calcula."
                    ),
                    action="Recorre la ruta de verificación en el Resumen.",
                    target="",
                )
            )

    # --- revisar: what the AI counted and the engine did not -----------
    faltantes = [f for f in (cobertura or []) if f.get("kind") == "faltante"]
    if faltantes:
        peor = max(faltantes, key=lambda f: f["ai_count"] - f["engine_count"])
        hallazgos.append(
            Hallazgo(
                id="cobertura_faltante",
                severity="revisar",
                title=(
                    "La IA cuenta más elementos que el motor en "
                    + (f"{len(faltantes)} hojas" if len(faltantes) > 1 else "una hoja")
                ),
                detail=(
                    f"El peor caso: en {peor['frame_code']} la lectura por imagen "
                    f"cuenta {peor['ai_count']} × {peor['family']} y el motor detectó "
                    f"{peor['engine_count']}. Un conteo no es una cantidad — señala "
                    "dónde mirar."
                ),
                action="Revisa esas hojas y registra lo que falte como elemento omitido.",
                target="revision",
                verificar=f"Abre la hoja {peor['frame_code']} y cuenta esa familia.",
                momento="cotizar",
            )
        )

    # --- the engine's remaining prose ----------------------------------
    # Repeats of one family collapse into a single finding carrying the whole
    # family's money: six copies of "this concept costs the wrong f'c" are one
    # decision, and printing them six times is how a list stops being read.
    seen: set[str] = set()
    criterios: list[str] = []
    grouped: dict[str, list[tuple[str, Rule, str | None]]] = {}
    for text in list(boq.warnings) + list(report.warnings):
        text = text.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        rule = _classify(text)
        if rule.criterio:
            # Not an alarm: nothing is asked of the reader. It belongs to the
            # assumptions register, where it defends the number instead of
            # diluting the tiers that need action.
            criterios.append(text)
            continue
        if rule.severity is None:
            continue  # a structural finding already says this, with numbers
        grouped.setdefault(rule.group or _stable_id(text), []).append(
            (text, rule, _concept_in(text))
        )

    for key, members in grouped.items():
        texts = [t for t, _r, _c in members]
        rule = members[0][1]
        severity = rule.severity
        if severity is None:  # unreachable: dropped above, but keeps the type honest
            continue
        codes = [c for _t, _r, c in members if c]
        # Money is only claimed where a priced line backs it; a finding that
        # cannot point at pesos says nothing about pesos.
        amounts = [by_code[c].amount for c in codes if c in by_code and not by_code[c].unpriced]
        monto = round(sum(amounts), 2) if amounts and severity == "bloqueante" else None
        if len(members) > 1 and rule.plural:
            title = rule.plural.format(n=len(members))
            detail = " · ".join(_headline(t, limit=90) for t in texts)
        else:
            title = _headline(texts[0])
            detail = texts[0] if len(texts[0]) > len(title) else ""
        hallazgos.append(
            Hallazgo(
                id=f"motor:{key}",
                severity=severity,
                title=title,
                detail=detail,
                action=rule.action,
                target=rule.target,
                monto_afectado=monto,
                concept_code=codes[0] if len(codes) == 1 else None,
                verificar=rule.verificar,
                momento=rule.momento,
            )
        )

    hallazgos.sort(
        key=lambda h: (
            SEVERITY_ORDER.get(h.severity, 9),
            -(h.monto_afectado or 0.0),
            h.title,
        )
    )
    # The engine's own assumptions belong in the same register as the notes.
    criterios.extend(a for a in boq.assumptions if a not in criterios)
    return _summarize(hallazgos, criterios, report)


def _summarize(
    hallazgos: list[Hallazgo], criterios: list[str], report: CostReport
) -> Diagnostico:
    by_severity: dict[str, int] = {}
    for h in hallazgos:
        by_severity[h.severity] = by_severity.get(h.severity, 0) + 1
    monto_en_duda = round(sum(h.monto_afectado or 0.0 for h in hallazgos), 2)
    sin_precio = sum(1 for h in hallazgos if h.id.startswith("sin_precio:"))
    bloqueantes = by_severity.get("bloqueante", 0)
    total = report.integration.grand_total

    parts: list[str] = []
    if not report.boq.units_reliable:
        parts.append(
            "Este presupuesto no tiene precios: el plano no declara una unidad confiable"
        )
    else:
        parts.append(f"{_money(total)} costeados")
    if sin_precio:
        parts.append(
            f"{sin_precio} concepto{'s' if sin_precio > 1 else ''} con cantidad y sin precio "
            "(el total no los incluye)"
        )
    if monto_en_duda > 0:
        parts.append(f"{_money(monto_en_duda)} en duda por conflictos con el plano")

    return Diagnostico(
        hallazgos=hallazgos,
        criterios=criterios,
        by_severity=by_severity,
        monto_en_duda=monto_en_duda,
        conceptos_sin_precio=sin_precio,
        entregable=bloqueantes == 0,
        resumen=" · ".join(parts) + ".",
    )
