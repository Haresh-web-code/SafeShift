from types import SimpleNamespace

import httpx
import pytest

from app import llm
from app.config import Settings


class APIError(Exception):
    def __init__(self, code: int):
        super().__init__(f"API error {code}")
        self.code = code


class FakeModels:
    def __init__(self, responses, stream_responses=None):
        self.responses = {model: list(values) for model, values in responses.items()}
        self.stream_responses = {
            model: list(values) for model, values in (stream_responses or {}).items()
        }
        self.content_calls = []
        self.stream_calls = []

    def generate_content(self, *, model, contents):
        self.content_calls.append(model)
        outcome = self.responses[model].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def generate_content_stream(self, *, model, contents):
        self.stream_calls.append(model)
        outcome = self.stream_responses[model].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _settings(
    *,
    retries: int = 1,
    fallback: str | None = None,
    deadline_ms: int = 1_000,
    timeout_ms: int = 200,
) -> Settings:
    return Settings(
        _env_file=None,
        gemini_api_key="not-a-real-key",
        gemini_model="configured-primary",
        gemini_fallback_model=fallback,
        gemini_max_retries=retries,
        gemini_deadline_ms=deadline_ms,
        gemini_timeout_ms=timeout_ms,
    )


def _response(text: str = "Grounded response"):
    return SimpleNamespace(
        text=text,
        usage_metadata=SimpleNamespace(
            prompt_token_count=12,
            candidates_token_count=7,
        ),
    )


def _install_fake_client(monkeypatch, settings, responses, stream_responses=None):
    models = FakeModels(responses, stream_responses)
    timeouts = []
    close_calls = []

    def create_client(api_key, timeout_ms):
        assert api_key == "not-a-real-key"
        timeouts.append(timeout_ms)
        return SimpleNamespace(models=models, close=lambda: close_calls.append(True))

    monkeypatch.setattr(llm, "get_settings", lambda: settings)
    monkeypatch.setattr(llm, "_create_client", create_client)
    monkeypatch.setattr(llm.time, "sleep", lambda seconds: None)
    return models, timeouts, close_calls


def test_successful_generation_returns_text_model_and_token_usage(monkeypatch):
    settings = _settings()
    models, timeouts, closed = _install_fake_client(
        monkeypatch,
        settings,
        {"configured-primary": [_response()]},
    )

    result = llm.generate_text_with_usage("Use only source passages")

    assert result.text == "Grounded response"
    assert result.model_used == "configured-primary"
    assert result.retry_count == 0
    assert result.prompt_tokens == 12
    assert result.completion_tokens == 7
    assert models.content_calls == ["configured-primary"]
    assert timeouts[0] <= settings.gemini_timeout_ms
    assert len(closed) == 1


def test_503_retries_are_bounded_by_configured_limit(monkeypatch):
    settings = _settings(retries=1)
    models, _, _ = _install_fake_client(
        monkeypatch,
        settings,
        {
            "configured-primary": [
                APIError(503),
                APIError(503),
            ]
        },
    )

    with pytest.raises(llm.GeminiError) as error:
        llm.generate_text_with_usage("prompt")

    assert models.content_calls == ["configured-primary", "configured-primary"]
    assert error.value.retry_count == 1


def test_read_timeout_is_retried_only_within_the_retry_limit(monkeypatch):
    settings = _settings(retries=1)
    models, timeouts, _ = _install_fake_client(
        monkeypatch,
        settings,
        {
            "configured-primary": [
                httpx.ReadTimeout("request timed out"),
                httpx.ReadTimeout("request timed out"),
            ]
        },
    )

    with pytest.raises(llm.GeminiError) as error:
        llm.generate_text_with_usage("prompt")

    assert error.value.retry_count == 1
    assert len(models.content_calls) == 2
    assert all(0 < timeout <= settings.gemini_timeout_ms for timeout in timeouts)


def test_expired_deadline_fails_before_making_a_request(monkeypatch):
    settings = _settings()
    models, _, _ = _install_fake_client(
        monkeypatch,
        settings,
        {"configured-primary": [_response()]},
    )

    with pytest.raises(llm.GeminiDeadlineExceeded):
        llm.generate_text_with_usage("prompt", deadline_ms=0)

    assert models.content_calls == []


def test_fallback_model_is_used_after_primary_transient_failure(monkeypatch):
    settings = _settings(retries=0, fallback="configured-fallback")
    models, _, _ = _install_fake_client(
        monkeypatch,
        settings,
        {
            "configured-primary": [APIError(503)],
            "configured-fallback": [_response("Fallback response")],
        },
    )

    result = llm.generate_text_with_usage("prompt")

    assert result.text == "Fallback response"
    assert result.model_used == "configured-fallback"
    assert result.retry_count == 1
    assert models.content_calls == [
        "configured-primary",
        "configured-fallback",
    ]


@pytest.mark.parametrize("status_code", [401, 403, 404])
def test_authentication_and_invalid_model_errors_are_not_retried(
    monkeypatch, status_code
):
    settings = _settings(retries=3, fallback="configured-fallback")
    models, _, _ = _install_fake_client(
        monkeypatch,
        settings,
        {
            "configured-primary": [APIError(status_code)],
            "configured-fallback": [_response()],
        },
    )

    with pytest.raises(llm.GeminiError) as error:
        llm.generate_text_with_usage("prompt")

    assert models.content_calls == ["configured-primary"]
    assert error.value.retry_count == 0


def test_missing_credentials_or_model_fail_before_client_creation(monkeypatch):
    monkeypatch.setattr(
        llm,
        "_create_client",
        lambda *args: pytest.fail("client must not be created for invalid config"),
    )

    for settings in (
        Settings(_env_file=None, gemini_model="configured-primary"),
        Settings(_env_file=None, gemini_api_key="not-a-real-key"),
    ):
        monkeypatch.setattr(llm, "get_settings", lambda settings=settings: settings)
        with pytest.raises(llm.GeminiConfigurationError):
            llm.generate_text_with_usage("prompt")


def test_legacy_timeout_and_retry_environment_names_are_supported(monkeypatch):
    monkeypatch.setenv("GEMINI_TIMEOUT", "650")
    monkeypatch.setenv("MAX_RETRIES", "2")

    settings = Settings(_env_file=None)

    assert settings.gemini_timeout_ms == 650
    assert settings.gemini_max_retries == 2


def test_stream_failure_after_partial_output_does_not_retry_or_use_fallback(
    monkeypatch,
):
    settings = _settings(retries=2, fallback="configured-fallback")

    def partial_then_fail():
        yield SimpleNamespace(text="first instruction")
        raise APIError(503)

    models, _, _ = _install_fake_client(
        monkeypatch,
        settings,
        {},
        {
            "configured-primary": [partial_then_fail()],
            "configured-fallback": [_response()],
        },
    )
    generation = llm.generate_text_stream_with_usage("prompt")

    with pytest.raises(llm.GeminiError):
        list(generation)

    assert generation.emitted_output
    assert generation.model_used == "configured-primary"
    assert generation.retry_count == 0
    assert models.stream_calls == ["configured-primary"]


def test_stream_retries_transient_error_before_emitting_any_text(monkeypatch):
    settings = _settings(retries=1, fallback="configured-fallback")
    models, _, _ = _install_fake_client(
        monkeypatch,
        settings,
        {},
        {
            "configured-primary": [APIError(503), APIError(503)],
            "configured-fallback": [
                [SimpleNamespace(text="fallback stream")]
            ],
        },
    )

    generation = llm.generate_text_stream_with_usage("prompt")
    assert list(generation) == ["fallback stream"]
    assert generation.model_used == "configured-fallback"
    assert generation.retry_count == 2
    assert models.stream_calls == [
        "configured-primary",
        "configured-primary",
        "configured-fallback",
    ]
