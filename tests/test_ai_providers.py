"""The AI reading picks its provider by configuration, honestly: an explicit
choice without credentials is 'not configured', never a silent fallback."""

import pytest
from klave_engine.llm.reader import (
    ANTHROPIC_MODEL,
    GEMINI_MODEL,
    SheetRead,
    active_model,
    credentials_available,
    gemini_reader,
    resolve_provider,
)


def _clear(monkeypatch):
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", "/nonexistent")  # no ~/.config/anthropic profile


def test_auto_prefers_claude_then_gemini(monkeypatch):
    _clear(monkeypatch)
    assert resolve_provider("auto") is None
    assert not credentials_available()
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    assert resolve_provider("auto") == "gemini"
    assert active_model() == GEMINI_MODEL
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a-key")
    assert resolve_provider("auto") == "anthropic"
    assert active_model() == ANTHROPIC_MODEL
    assert active_model(model="mi-modelo") == "mi-modelo"


def test_an_explicit_choice_never_falls_back(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a-key")
    # Gemini asked for, Gemini not configured: not configured — not Claude.
    assert resolve_provider("gemini") is None
    assert not credentials_available("gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    assert resolve_provider("gemini") == "gemini"
    assert active_model("gemini") == GEMINI_MODEL


def test_gemini_reader_parses_the_structured_response(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    from klave_engine.llm.reader import _FamilyValue, _GeminiSheetRead

    class FakeUsage:
        prompt_token_count = 1234
        candidates_token_count = 88

    class FakeResponse:
        # The wire model: the Gemini Developer API rejects dict fields
        # (additionalProperties), so fc/cover travel as keyed lists.
        parsed = _GeminiSheetRead(
            sheet_code="ES-100",
            title="PLANTA BAJA",
            concrete_fc=[_FamilyValue(family="losa", value=250)],
        )
        usage_metadata = FakeUsage()

    class FakeModels:
        def generate_content(self, *, model, contents, config):
            assert model == GEMINI_MODEL
            assert config.response_schema is _GeminiSheetRead
            def keys_of(node):
                if isinstance(node, dict):
                    yield from node
                    for child in node.values():
                        yield from keys_of(child)
                elif isinstance(node, list):
                    for child in node:
                        yield from keys_of(child)

            assert "additionalProperties" not in set(
                keys_of(_GeminiSheetRead.model_json_schema())
            )
            return FakeResponse()

    class FakeClient:
        models = FakeModels()

    read = gemini_reader(client=FakeClient())
    parsed, usage = read(b"\x89PNG fake", "Hoja ES-100")
    assert isinstance(parsed, SheetRead)
    assert parsed.sheet_code == "ES-100"
    assert parsed.concrete_fc == {"losa": 250}
    assert usage == {"input_tokens": 1234, "output_tokens": 88}


# ── Claude: lo que se le pide y lo que se hace con lo que devuelve ──────────


class _Usage:
    input_tokens = 1200
    output_tokens = 340


class _FakeBetaMessages:
    def __init__(self, response):
        self.response = response
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return self.response

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class _FakeAnthropic:
    def __init__(self, response):
        self.beta = type("Beta", (), {})()
        self.beta.messages = _FakeBetaMessages(response)


def _respuesta(**campos):
    base = {"stop_reason": "end_turn", "stop_details": None, "usage": _Usage(),
            "parsed_output": None, "content": []}
    base.update(campos)
    return type("Respuesta", (), base)()


def test_la_lectura_de_claude_pide_opus_5_5_con_respaldo_y_esfuerzo_alto():
    from klave_engine.llm.reader import anthropic_reader

    leida = SheetRead(sheet_code="ES-100")
    client = _FakeAnthropic(_respuesta(parsed_output=leida))
    parsed, usage = anthropic_reader(client=client)(b"\x89PNG fake", "Hoja ES-100")
    assert parsed.sheet_code == "ES-100"
    assert usage == {"input_tokens": 1200, "output_tokens": 340}
    call = client.beta.messages.calls[0]
    assert call["model"] == "claude-opus-5-5" == ANTHROPIC_MODEL
    assert call["fallbacks"] == "default"
    assert call["betas"] == ["server-side-fallback-2026-07-01"]
    assert call["output_format"] is SheetRead
    assert call["output_config"] == {"effort": "high"}
    assert call["messages"][-1]["role"] == "user"  # sin prefill: el último turno es del usuario


def test_una_negativa_de_claude_es_un_error_que_se_dice_no_una_lectura_vacía():
    from klave_engine.llm.reader import anthropic_reader, is_transient

    detalles = type("Detalles", (), {"category": "cyber", "explanation": None})()
    client = _FakeAnthropic(_respuesta(stop_reason="refusal", stop_details=detalles))
    with pytest.raises(ValueError) as info:
        anthropic_reader(client=client)(b"\x89PNG fake", "Hoja ES-100")
    assert "declinó" in str(info.value) and "cyber" in str(info.value)
    assert not is_transient(info.value)  # repetirla no la cambia


def test_el_copiloto_de_claude_tiene_espacio_para_pensar_y_responder():
    from klave_engine.llm.reader import anthropic_asker

    texto = type("Bloque", (), {"type": "text", "text": "Hola"})()
    pensado = type("Bloque", (), {"type": "thinking", "thinking": ""})()
    client = _FakeAnthropic(_respuesta(content=[pensado, texto]))
    assert anthropic_asker(client=client)("sistema", "pregunta") == "Hola"
    call = client.beta.messages.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["max_tokens"] >= 16000  # el pensamiento cuenta contra max_tokens
    assert call["fallbacks"] == "default"


def test_un_modelo_de_otro_proveedor_en_la_configuración_no_se_le_manda_al_que_no_es(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a-key")
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    # KLAVE_AI_MODEL=gemini-3.7-flash quedó de cuando se usaba Gemini.
    assert active_model("anthropic", "gemini-3.7-flash") == ANTHROPIC_MODEL
    assert active_model("gemini", "claude-opus-5-5") == GEMINI_MODEL
    assert active_model("anthropic", "claude-sonnet-5-5") == "claude-sonnet-5-5"


def test_la_tarifa_de_opus_5_5_está_declarada():
    from klave_engine.llm.tarifas import tarifa_de

    t = tarifa_de("claude-opus-5-5")
    assert t is not None and (t.entrada_por_millon, t.salida_por_millon) == (4.00, 20.00)
