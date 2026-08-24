"""The AI reading picks its provider by configuration, honestly: an explicit
choice without credentials is 'not configured', never a silent fallback."""

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

    class FakeUsage:
        prompt_token_count = 1234
        candidates_token_count = 88

    class FakeResponse:
        parsed = SheetRead(sheet_code="ES-100", title="PLANTA BAJA")
        usage_metadata = FakeUsage()

    class FakeModels:
        def generate_content(self, *, model, contents, config):
            assert model == GEMINI_MODEL
            assert config.response_schema is SheetRead
            return FakeResponse()

    class FakeClient:
        models = FakeModels()

    read = gemini_reader(client=FakeClient())
    parsed, usage = read(b"\x89PNG fake", "Hoja ES-100")
    assert parsed.sheet_code == "ES-100"
    assert usage == {"input_tokens": 1234, "output_tokens": 88}
