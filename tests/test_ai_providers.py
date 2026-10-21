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
    from klave_engine.llm.reader import _ClaudeSheetRead, anthropic_reader

    leida = _ClaudeSheetRead(
        sheet_code="ES-100", title="", level="", scale="", concrete_fc=[], steel_fy=None,
        cover_cm=[], desplante_m=None, slab_system="", elements=[], conteo=[], notes=[],
        uncertainties=[],
    )
    client = _FakeAnthropic(_respuesta(parsed_output=leida))
    parsed, usage = anthropic_reader(client=client)(b"\x89PNG fake", "Hoja ES-100")
    assert parsed.sheet_code == "ES-100"
    assert usage == {"input_tokens": 1200, "output_tokens": 340}
    call = client.beta.messages.calls[0]
    assert call["model"] == "claude-opus-5-5" == ANTHROPIC_MODEL
    assert call["fallbacks"] == "default"
    assert call["betas"] == ["server-side-fallback-2026-07-01"]
    assert call["output_format"].__name__ == "_ClaudeSheetRead"
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


def test_una_llave_sin_espacio_de_trabajo_lleva_el_encabezado_si_se_declara(monkeypatch):
    """Una llave de la consola que no está ligada a un workspace exige el
    encabezado anthropic-workspace-id; ANTHROPIC_WORKSPACE_ID lo pone."""
    from klave_engine.llm.reader import _cliente_anthropic

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-prueba")
    monkeypatch.delenv("ANTHROPIC_WORKSPACE_ID", raising=False)
    assert "anthropic-workspace-id" not in _cliente_anthropic().default_headers
    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", " wrkspc_123 ")
    assert _cliente_anthropic().default_headers["anthropic-workspace-id"] == "wrkspc_123"


def test_el_esquema_que_va_a_claude_cabe_en_los_límites_de_salida_estructurada():
    """La API compila el esquema a una gramática: cada parámetro opcional y cada
    unión (anyOf / nullable) la multiplica; con 19 opcionales y 13 uniones
    respondía 400 «Schema is too complex». Y un dict[str, int] llegaba como un
    objeto vacío (additionalProperties: false): f'c y recubrimientos no cabían."""
    import json

    from anthropic.lib._parse._transform import transform_schema
    from klave_engine.llm.reader import _ClaudeSheetRead

    esquema = transform_schema(_ClaudeSheetRead)

    def objetos(nodo):
        if isinstance(nodo, dict):
            if nodo.get("type") == "object":
                yield nodo
            for valor in nodo.values():
                yield from objetos(valor)
        elif isinstance(nodo, list):
            for valor in nodo:
                yield from objetos(valor)

    opcionales = sum(
        len(set(o.get("properties", {})) - set(o.get("required", []))) for o in objetos(esquema)
    )
    uniones = json.dumps(esquema).count('"anyOf"')
    vacios = [o for o in objetos(esquema) if o.get("properties") == {}]
    assert opcionales == 0 and uniones <= 3 and not vacios


def test_la_lectura_de_claude_vuelve_a_la_forma_de_siempre():
    from klave_engine.llm.reader import _ClaudeSheetRead, anthropic_reader

    wire = _ClaudeSheetRead.model_validate({
        "sheet_code": "ES-100", "title": "", "level": "PLANTA BAJA", "scale": "",
        "concrete_fc": [{"family": "losa", "value": 250}], "steel_fy": 4200,
        "cover_cm": [{"family": "castillo", "value": 3}], "desplante_m": None,
        "slab_system": "",
        "elements": [{"mark": "K-1", "family": "castillo", "section_cm": "15x15", "rebar": "4#3",
                      "stirrups": "", "length_m": None, "note": "", "confidence": 0.9}],
        "conteo": [{"family": "castillo", "drawn_count": 12, "note": ""}],
        "notes": [], "uncertainties": [],
    })
    client = _FakeAnthropic(_respuesta(parsed_output=wire))
    leida, _ = anthropic_reader(client=client)(b"\x89PNG fake", "Hoja ES-100")
    assert isinstance(leida, SheetRead)
    assert leida.concrete_fc == {"losa": 250} and leida.cover_cm == {"castillo": 3.0}
    assert leida.title is None and leida.slab_system is None  # «» es «no aparece»
    assert leida.elements[0].stirrups is None and leida.elements[0].rebar == "4#3"
    assert leida.conteo[0].note is None
    assert client.beta.messages.calls[0]["output_format"] is _ClaudeSheetRead
