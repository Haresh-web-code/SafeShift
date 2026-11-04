import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx
from google import genai
from google.genai import types

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
BACKOFF_BASE_SECONDS = 0.1
BACKOFF_MAX_SECONDS = 0.5


class GeminiError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        model_used: str | None = None,
        retry_count: int = 0,
    ) -> None:
        super().__init__(message)
        self.model_used = model_used
        self.retry_count = retry_count


class GeminiConfigurationError(GeminiError):
    pass


class GeminiDeadlineExceeded(GeminiError):
    pass


@dataclass(frozen=True)
class GenerationResult:
    text: str
    model_used: str
    retry_count: int
    prompt_tokens: int | None
    completion_tokens: int | None


def validate_gemini_config(settings: Settings | None = None) -> tuple[str, list[str]]:
    settings = settings or get_settings()
    api_key = settings.gemini_api_key
    if api_key is None or not api_key.get_secret_value().strip():
        raise GeminiConfigurationError("Gemini API key is not configured")

    primary_model = (settings.gemini_model or "").strip()
    if not primary_model:
        raise GeminiConfigurationError("Gemini model is not configured")

    models = [primary_model]
    fallback_model = (settings.gemini_fallback_model or "").strip()
    if fallback_model and fallback_model != primary_model:
        models.append(fallback_model)

    return api_key.get_secret_value(), models


def _create_client(api_key: str, timeout_ms: int) -> genai.Client:
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            timeout=timeout_ms,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )


def _token_count(response: Any, field: str) -> int | None:
    usage = getattr(response, "usage_metadata", None)
    count = getattr(usage, field, None)
    return count if isinstance(count, int) and count >= 0 else None


def _status_code(exc: Exception) -> int | None:
    for candidate in (
        getattr(exc, "code", None),
        getattr(exc, "status_code", None),
        getattr(getattr(exc, "response", None), "status_code", None),
    ):
        try:
            if candidate is not None:
                return int(candidate)
        except (TypeError, ValueError):
            continue
    return None


def is_retryable_error(exc: Exception) -> bool:
    status_code = _status_code(exc)
    if status_code is not None:
        return status_code in RETRYABLE_STATUS_CODES

    return isinstance(
        exc,
        (
            TimeoutError,
            ConnectionError,
            httpx.TimeoutException,
            httpx.NetworkError,
        ),
    )


def _backoff_seconds(attempt: int) -> float:
    return min(BACKOFF_BASE_SECONDS * (2**attempt), BACKOFF_MAX_SECONDS)


def _remaining_ms(deadline: float) -> int:
    return max(0, int((deadline - time.monotonic()) * 1000))


def _raise_failure(
    exc: Exception,
    *,
    model_used: str | None,
    retry_count: int,
) -> None:
    if isinstance(exc, GeminiError):
        raise exc
    raise GeminiError(
        "Gemini generation failed",
        model_used=model_used,
        retry_count=retry_count,
    ) from exc


def generate_text_with_usage(
    prompt: str,
    *,
    deadline_ms: int | None = None,
) -> GenerationResult:
    settings = get_settings()
    api_key, models = validate_gemini_config(settings)
    deadline = time.monotonic() + min(
        settings.gemini_deadline_ms,
        deadline_ms if deadline_ms is not None else settings.gemini_deadline_ms,
    ) / 1000
    attempts = 0
    model_used: str | None = None
    last_error: Exception | None = None

    for model in models:
        for retry in range(settings.gemini_max_retries + 1):
            remaining_ms = _remaining_ms(deadline)
            if remaining_ms <= 0:
                break

            model_used = model
            attempts += 1
            client = _create_client(
                api_key,
                min(settings.gemini_timeout_ms, remaining_ms),
            )
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                )
                text = response.text
                if not text or not text.strip():
                    raise GeminiError(
                        "Gemini returned an empty response",
                        model_used=model,
                        retry_count=attempts - 1,
                    )

                return GenerationResult(
                    text=text,
                    model_used=model,
                    retry_count=attempts - 1,
                    prompt_tokens=_token_count(response, "prompt_token_count"),
                    completion_tokens=_token_count(response, "candidates_token_count"),
                )
            except Exception as exc:
                if not is_retryable_error(exc):
                    _raise_failure(
                        exc,
                        model_used=model,
                        retry_count=attempts - 1,
                    )

                last_error = exc
                if retry >= settings.gemini_max_retries:
                    break

                delay = _backoff_seconds(retry)
                if _remaining_ms(deadline) <= int(delay * 1000):
                    break

                logger.warning(
                    "Gemini transient failure model=%s status_code=%s retry_count=%s",
                    model,
                    _status_code(exc),
                    attempts,
                )
                time.sleep(delay)
            finally:
                client.close()

    retry_count = attempts - 1
    if _remaining_ms(deadline) <= 0:
        raise GeminiDeadlineExceeded(
            "Gemini generation deadline exceeded",
            model_used=model_used,
            retry_count=retry_count,
        ) from last_error

    raise GeminiError(
        "Gemini generation failed for configured models",
        model_used=model_used,
        retry_count=retry_count,
    ) from last_error


@dataclass
class StreamGeneration:
    prompt: str
    settings: Settings
    deadline_ms: int | None = None
    model_used: str | None = None
    retry_count: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    emitted_output: bool = False

    def __iter__(self) -> Iterator[str]:
        return self._generate()

    def _generate(self) -> Iterator[str]:
        api_key, models = validate_gemini_config(self.settings)
        deadline = time.monotonic() + min(
            self.settings.gemini_deadline_ms,
            self.deadline_ms
            if self.deadline_ms is not None
            else self.settings.gemini_deadline_ms,
        ) / 1000
        attempts = 0
        last_error: Exception | None = None

        for model in models:
            for retry in range(self.settings.gemini_max_retries + 1):
                remaining_ms = _remaining_ms(deadline)
                if remaining_ms <= 0:
                    break

                self.model_used = model
                attempts += 1
                self.retry_count = attempts - 1
                client = _create_client(
                    api_key,
                    min(self.settings.gemini_timeout_ms, remaining_ms),
                )
                saw_text = False
                try:
                    chunks = client.models.generate_content_stream(
                        model=model,
                        contents=self.prompt,
                    )
                    for chunk in chunks:
                        if _remaining_ms(deadline) <= 0:
                            raise GeminiDeadlineExceeded(
                                "Gemini stream deadline exceeded",
                                model_used=model,
                                retry_count=attempts - 1,
                            )
                        prompt_tokens = _token_count(chunk, "prompt_token_count")
                        if prompt_tokens is not None:
                            self.prompt_tokens = prompt_tokens
                        completion_tokens = _token_count(
                            chunk, "candidates_token_count"
                        )
                        if completion_tokens is not None:
                            self.completion_tokens = completion_tokens
                        text = chunk.text
                        if text:
                            saw_text = True
                            self.emitted_output = True
                            yield text

                    if not saw_text:
                        raise GeminiError(
                            "Gemini returned an empty stream",
                            model_used=model,
                            retry_count=attempts - 1,
                        )
                    if _remaining_ms(deadline) <= 0:
                        raise GeminiDeadlineExceeded(
                            "Gemini stream deadline exceeded",
                            model_used=model,
                            retry_count=attempts - 1,
                        )
                    return
                except Exception as exc:
                    if self.emitted_output or not is_retryable_error(exc):
                        _raise_failure(
                            exc,
                            model_used=model,
                            retry_count=attempts - 1,
                        )

                    last_error = exc
                    if retry >= self.settings.gemini_max_retries:
                        break

                    delay = _backoff_seconds(retry)
                    if _remaining_ms(deadline) <= int(delay * 1000):
                        break

                    logger.warning(
                        "Gemini transient stream failure model=%s status_code=%s retry_count=%s",
                        model,
                        _status_code(exc),
                        attempts,
                    )
                    time.sleep(delay)
                finally:
                    client.close()

        self.retry_count = attempts - 1
        if _remaining_ms(deadline) <= 0:
            raise GeminiDeadlineExceeded(
                "Gemini stream deadline exceeded",
                model_used=self.model_used,
                retry_count=self.retry_count,
            ) from last_error

        raise GeminiError(
            "Gemini streaming failed for configured models",
            model_used=self.model_used,
            retry_count=self.retry_count,
        ) from last_error


def generate_text_stream_with_usage(
    prompt: str,
    *,
    deadline_ms: int | None = None,
) -> StreamGeneration:
    return StreamGeneration(prompt, get_settings(), deadline_ms)


def generate_text(prompt: str) -> str:
    return generate_text_with_usage(prompt).text


def generate_text_stream(prompt: str) -> Iterator[str]:
    yield from generate_text_stream_with_usage(prompt)


def list_available_models() -> list[str]:
    settings = get_settings()
    api_key, _ = validate_gemini_config(settings)
    client = _create_client(api_key, settings.gemini_timeout_ms)
    try:
        return [
            model.name
            for model in client.models.list()
            if "generateContent" in (getattr(model, "supported_actions", None) or [])
        ]
    finally:
        client.close()


def test_gemini_connection() -> GenerationResult:
    return generate_text_with_usage("Reply with exactly: SafeShift connection successful")
