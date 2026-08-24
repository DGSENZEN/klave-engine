"""LLM-assisted reading of a sheet image: what the rules cannot read.

A vision model reads a rendered frame the way an engineer would — the
cajetín, the cuadro de castillos, the notes (f'c, fy, recubrimientos,
desplante), the element marks and their sections — and returns a
structured reading. Everything it returns is a *suggestion with
provenance* ("leído por IA de la imagen de la hoja"): it is stored beside
the rule-based reading, shown to the engineer to confirm, and ranks below
a cuadro, a detalle or a nota the rules read themselves. It never prices
anything and never becomes a quantity on its own.

Two providers, one contract: Claude (ANTHROPIC_API_KEY or an `ant auth
login` profile) and Gemini (GEMINI_API_KEY / GOOGLE_API_KEY). The provider
is chosen with KLAVE_AI_PROVIDER (anthropic | gemini | auto — auto prefers
whichever has credentials, Claude first) and the model can be overridden
with KLAVE_AI_MODEL. Without credentials the feature reports itself as not
configured rather than failing.
"""

from __future__ import annotations

import base64
import time
from collections.abc import Callable
from typing import Any, cast

from pydantic import BaseModel, Field

ANTHROPIC_MODEL = "claude-opus-5"
GEMINI_MODEL = "gemini-2.5-pro"
MODEL = ANTHROPIC_MODEL  # backwards-compatible alias

# How a failed sheet reads in its own uncertainties: the marker that lets a
# later run find exactly which sheets are worth asking for again.
FAILED_PREFIX = "No se pudo leer la hoja"
RETRY_BASE_SECONDS = 2.0
RETRY_FACTOR = 3.0

# Provider errors that mean "busy, ask again", not "wrong, stop asking".
_TRANSIENT_MARKERS = (
    "503", "429", "unavailable", "resource_exhausted", "resource exhausted",
    "overloaded", "high demand", "rate limit", "too many requests", "quota",
    "timeout", "timed out", "deadline", "temporarily", "internal error",
    "connection reset", "connection aborted",
)


def is_transient(error: BaseException | str) -> bool:
    """Whether asking again could plausibly work. An unknown model, a bad key
    or a rejected schema never improves by repetition — those fail once."""
    return any(marker in str(error).lower() for marker in _TRANSIENT_MARKERS)


SYSTEM_PROMPT = """Eres un ingeniero de costos mexicano leyendo una hoja de un plano de \
construcción (imagen renderizada desde el DWG). Lee únicamente lo que está escrito o \
dibujado en la hoja. No inventes valores: si un dato no aparece, déjalo vacío. Las \
secciones se expresan en centímetros como base x peralte (p. ej. 30x80). Los armados \
como aparecen (p. ej. 4#4 E#2@20). Indica tu confianza por campo entre 0 y 1."""


class ElementRead(BaseModel):
    """One element type as the sheet declares it (cuadro, detalle or note)."""

    mark: str = Field(description="Marca del elemento tal como aparece: K-1, T1-8, CTA-16, MC-2")
    family: str = Field(
        description="castillo | columna | trabe | contratrabe | dala | cerramiento | zapata | "
        "dado | pilote | muro_concreto | losa | otro"
    )
    section_cm: str | None = Field(default=None, description="base x peralte en cm, p. ej. 30x80")
    rebar: str | None = Field(default=None, description="armado longitudinal, p. ej. 4#4")
    stirrups: str | None = Field(default=None, description="estribos, p. ej. E#2@20")
    length_m: float | None = Field(default=None, description="longitud declarada en m (pilotes)")
    note: str | None = Field(default=None, description="texto de donde se leyó, abreviado")
    confidence: float = Field(ge=0, le=1)


class FamilyCount(BaseModel):
    """How many instances of a family are DRAWN on the sheet.

    This is the coverage audit: the model's count is compared against the
    rule detectors' count per sheet, and a disagreement flags the sheet for
    the engineer to look at. The count never becomes a quantity — it only
    points at what the engine may have missed.
    """

    family: str = Field(
        description="castillo | columna | trabe | contratrabe | dala | cerramiento | "
        "zapata | pilote | escalera"
    )
    drawn_count: int = Field(
        ge=0,
        description="instancias DIBUJADAS en la planta (símbolos o marcas repetidas); "
        "los renglones de un cuadro y las viñetas de detalle NO cuentan",
    )
    note: str | None = Field(default=None, description="dónde se concentran, si ayuda")


class SheetRead(BaseModel):
    """What the model read from one sheet image."""

    sheet_code: str | None = Field(default=None, description="Clave en el cajetín: ES-100")
    title: str | None = Field(default=None, description="Título de la hoja en el cajetín")
    level: str | None = Field(default=None, description="Nivel o planta: PLANTA BAJA, N+3.20")
    scale: str | None = Field(default=None, description="Escala declarada: 1:50")
    concrete_fc: dict[str, int] = Field(
        default_factory=dict,
        description="f'c en kg/cm² por familia: {'cimentacion': 250, 'losa': 250, 'castillo': 200}",
    )
    steel_fy: int | None = Field(default=None, description="fy del acero en kg/cm²")
    cover_cm: dict[str, float] = Field(
        default_factory=dict, description="recubrimientos en cm por familia"
    )
    desplante_m: float | None = Field(default=None, description="profundidad de desplante en m")
    slab_system: str | None = Field(
        default=None, description="sistema de losa declarado: vigueta y bovedilla 12-5, reticular…"
    )
    elements: list[ElementRead] = Field(default_factory=list)
    conteo: list[FamilyCount] = Field(
        default_factory=list,
        description="conteo por familia de instancias dibujadas en la planta; vacío "
        "en hojas de puros detalles/cuadros",
    )
    notes: list[str] = Field(default_factory=list, description="notas generales relevantes")
    uncertainties: list[str] = Field(
        default_factory=list, description="lo ilegible o dudoso en la imagen"
    )


class SheetReading(BaseModel):
    """A SheetRead with its provenance: which frame, which model, when."""

    frame_code: str
    frame_title: str = ""
    model: str = MODEL
    read: SheetRead
    input_tokens: int = 0
    output_tokens: int = 0


# A function that takes (png bytes, prompt) and returns (SheetRead, usage) — the
# Anthropic call by default, anything else in tests.
Reader = Callable[[bytes, str], tuple[SheetRead, dict[str, int]]]


def failed_reading(reading: SheetReading) -> bool:
    """Whether this sheet's reading is a recorded failure, not a reading."""
    return any(u.startswith(FAILED_PREFIX) for u in reading.read.uncertainties)


def _anthropic_credentials() -> bool:
    import os

    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    profile_dir = os.path.expanduser("~/.config/anthropic")
    return os.path.isdir(profile_dir) and any(os.scandir(profile_dir))


def _gemini_credentials() -> bool:
    import os

    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))


def resolve_provider(provider: str | None = None) -> str | None:
    """The provider that will serve readings, or None when none can.

    An explicit choice is honored only if its credentials exist (a wrong
    KLAVE_AI_PROVIDER must say "not configured", not fall back silently to
    another vendor the operator did not choose)."""
    choice = (provider or "auto").strip().lower()
    if choice == "anthropic":
        return "anthropic" if _anthropic_credentials() else None
    if choice == "gemini":
        return "gemini" if _gemini_credentials() else None
    if _anthropic_credentials():
        return "anthropic"
    if _gemini_credentials():
        return "gemini"
    return None


def credentials_available(provider: str | None = None) -> bool:
    """Whether some provider can serve readings without a network call."""
    return resolve_provider(provider) is not None


def active_model(provider: str | None = None, model: str | None = None) -> str | None:
    resolved = resolve_provider(provider)
    if resolved is None:
        return None
    if model:
        return model
    return ANTHROPIC_MODEL if resolved == "anthropic" else GEMINI_MODEL


def configured_reader(provider: str | None = None, model: str | None = None) -> Reader:
    """The reader for the configured provider; raises when none is set up."""
    resolved = resolve_provider(provider)
    if resolved == "anthropic":
        return anthropic_reader(model=model or ANTHROPIC_MODEL)
    if resolved == "gemini":
        return gemini_reader(model=model or GEMINI_MODEL)
    raise RuntimeError("La lectura con IA no está configurada (sin credenciales).")


class _FamilyValue(BaseModel):
    family: str
    value: float


class _GeminiSheetRead(BaseModel):
    """SheetRead's wire shape for the Gemini Developer API, which rejects
    open-ended dict fields in a response schema. The two dicts travel as
    keyed lists here and convert back on arrival."""

    sheet_code: str | None = None
    title: str | None = None
    level: str | None = None
    scale: str | None = None
    concrete_fc: list[_FamilyValue] = Field(
        default_factory=list,
        description="f'c en kg/cm² por familia: family cimentacion|losa|castillo|…, value 250",
    )
    steel_fy: int | None = None
    cover_cm: list[_FamilyValue] = Field(
        default_factory=list, description="recubrimientos en cm por familia"
    )
    desplante_m: float | None = None
    slab_system: str | None = None
    elements: list[ElementRead] = Field(default_factory=list)
    conteo: list[FamilyCount] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)

    def to_sheet_read(self) -> SheetRead:
        data = self.model_dump()
        data["concrete_fc"] = {e.family: int(e.value) for e in self.concrete_fc if e.family}
        data["cover_cm"] = {e.family: e.value for e in self.cover_cm if e.family}
        return SheetRead.model_validate(data)


def gemini_reader(client: Any | None = None, model: str = GEMINI_MODEL) -> Reader:
    """The Gemini reader: same contract, structured output via response_schema."""
    from google import genai
    from google.genai import types

    sdk = client or genai.Client()

    def read(png: bytes, prompt: str) -> tuple[SheetRead, dict[str, int]]:
        # The SDK's contents union is wider than what we build; mypy's list
        # invariance rejects the narrower element type, so cast once here.
        contents = cast(
            "Any",
            [types.Part.from_bytes(data=png, mime_type="image/png"), prompt],
        )
        response = sdk.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=_GeminiSheetRead,
            ),
        )
        parsed = response.parsed
        if parsed is None:
            # Some responses come back as raw JSON text instead of parsed.
            text = getattr(response, "text", None)
            if not text:
                raise ValueError("el modelo no devolvió una lectura estructurada")
            parsed = _GeminiSheetRead.model_validate_json(text)
        if not isinstance(parsed, _GeminiSheetRead):
            parsed = _GeminiSheetRead.model_validate(parsed)
        meta = getattr(response, "usage_metadata", None)
        usage = {
            "input_tokens": int(getattr(meta, "prompt_token_count", 0) or 0),
            "output_tokens": int(getattr(meta, "candidates_token_count", 0) or 0),
        }
        return parsed.to_sheet_read(), usage

    return read


def anthropic_reader(client: Any | None = None, model: str = ANTHROPIC_MODEL) -> Reader:
    """The Claude reader: one vision request per sheet image, structured
    output validated against SheetRead."""
    import anthropic

    sdk = client or anthropic.Anthropic()

    def read(png: bytes, prompt: str) -> tuple[SheetRead, dict[str, int]]:
        response = sdk.messages.parse(
            model=model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            thinking={"type": "adaptive"},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": base64.standard_b64encode(png).decode("ascii"),
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            output_format=SheetRead,
        )
        parsed = response.parsed_output
        if parsed is None:
            raise ValueError("el modelo no devolvió una lectura estructurada")
        usage = {
            "input_tokens": int(getattr(response.usage, "input_tokens", 0) or 0),
            "output_tokens": int(getattr(response.usage, "output_tokens", 0) or 0),
        }
        return parsed, usage

    return read


# A plain text ask: (system, prompt) -> text. The copilot uses this; the
# sheet reader above uses the vision path.
Asker = Callable[[str, str], str]


def configured_asker(provider: str | None = None, model: str | None = None) -> Asker:
    """Text completion from whichever provider is configured, same rules as
    the reader: an explicit choice without credentials never falls back."""
    resolved = resolve_provider(provider)
    if resolved == "anthropic":
        return anthropic_asker(model=model or ANTHROPIC_MODEL)
    if resolved == "gemini":
        return gemini_asker(model=model or GEMINI_MODEL)
    raise RuntimeError("El copiloto no está configurado (sin credenciales de IA).")


def gemini_asker(client: Any | None = None, model: str = GEMINI_MODEL) -> Asker:
    from google import genai
    from google.genai import types

    sdk = client or genai.Client()

    def ask(system: str, prompt: str) -> str:
        response = sdk.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=system),
        )
        return getattr(response, "text", "") or ""

    return ask


def anthropic_asker(client: Any | None = None, model: str = ANTHROPIC_MODEL) -> Asker:
    import anthropic

    sdk = client or anthropic.Anthropic()

    def ask(system: str, prompt: str) -> str:
        response = sdk.messages.create(
            model=model,
            max_tokens=1200,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        # The SDK's block union is wider than the text blocks we asked for.
        return "".join(
            str(getattr(block, "text", ""))
            for block in response.content
            if getattr(block, "type", "") == "text"
        )

    return ask


def frame_prompt(code: str, title: str, kind: str) -> str:
    if kind == "plan":
        what = (
            "una planta estructural: lee el cajetín, el nivel, las notas y las marcas de "
            "elementos. Además llena conteo: cuenta por familia cuántas instancias están "
            "DIBUJADAS en la planta (cada símbolo o marca repetida es una instancia; los "
            "renglones de un cuadro y las viñetas de detalle NO cuentan)"
        )
    else:
        what = (
            "una hoja de detalles/notas/cuadros: lee cada marca con su sección y armado; "
            "deja conteo vacío (aquí no hay instancias en planta)"
        )
    return (
        f"Hoja {code} «{title}». Es {what}. Devuelve la lectura estructurada; deja vacío lo "
        "que no esté escrito en la imagen y anota en uncertainties lo que no se distinga."
    )


def read_frames(
    renders: list[tuple[str, str, str, bytes]],
    reader: Reader,
    on_reading: Callable[[SheetReading], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    model: str = MODEL,
    max_attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
    cooldown_seconds: float = 5.0,
) -> list[SheetReading]:
    """Read every (code, title, kind, png) with the reader; a failure on one
    sheet is recorded as an uncertainty, not a crash of the batch.
    ``on_reading`` hears each sheet as it lands (progress); ``should_stop``
    is asked before each sheet so a cancel keeps what was already read.

    A *transient* provider error (busy, rate-limited) is retried with growing
    pauses, and after a sheet exhausts its attempts the batch waits once more
    before the next one — asking a saturated model faster only makes it worse.
    A permanent error (unknown model, bad key, rejected schema) fails at the
    first try: repeating it wastes the quota that the other sheets need."""
    readings: list[SheetReading] = []
    for code, title, kind, png in renders:
        if should_stop is not None and should_stop():
            break
        prompt = frame_prompt(code, title, kind)
        read: SheetRead | None = None
        usage: dict[str, int] = {}
        last_error: BaseException | None = None
        for attempt in range(1, max(1, max_attempts) + 1):
            try:
                read, usage = reader(png, prompt)
                break
            except Exception as exc:  # noqa: BLE001 — one bad sheet must not sink the batch
                last_error = exc
                if attempt >= max_attempts or not is_transient(exc):
                    break
                sleep(min(RETRY_BASE_SECONDS * RETRY_FACTOR ** (attempt - 1), 30.0))
        if read is None:
            read = SheetRead(uncertainties=[f"{FAILED_PREFIX}: {last_error}"[:200]])
            usage = {}
            if last_error is not None and is_transient(last_error):
                sleep(cooldown_seconds)
        reading = SheetReading(
            frame_code=code, frame_title=title, model=model, read=read,
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
        )
        readings.append(reading)
        if on_reading is not None:
            on_reading(reading)
    return readings
