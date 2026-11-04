import json

import pytest

from app import llm, main
from app.config import Settings
from app.llm import GeminiDeadlineExceeded, GenerationResult
from app.usage import UsageTracker


@pytest.fixture
def retrieved_passage():
    return (
        3,
        {
            "document": "OSHA3120.pdf",
            "page": 12,
            "chunk_id": 1,
            "text": "The employer shall prepare for shutdown before servicing equipment.",
        },
    )


def _generation(
    text: str = "Follow the documented shutdown steps.",
) -> GenerationResult:
    return GenerationResult(
        text=text,
        model_used="configured-test-model",
        retry_count=0,
        prompt_tokens=100,
        completion_tokens=50,
    )


def _sse_payloads(response_text: str, event_name: str) -> list[dict]:
    payloads = []
    for event in response_text.strip().split("\n\n"):
        if f"event: {event_name}\n" in event:
            data_line = next(line for line in event.splitlines() if line.startswith("data: "))
            payloads.append(json.loads(data_line.removeprefix("data: ")))
    return payloads


def test_chat_returns_structured_answer_and_timings(
    client, monkeypatch, retrieved_passage
):
    monkeypatch.setattr(
        main, "search", lambda question, top_k: ([retrieved_passage], {})
    )
    monkeypatch.setattr(
        main, "generate_text_with_usage", lambda prompt, deadline_ms: _generation()
    )

    response = client.post(
        "/chat",
        json={"question": "What should happen before servicing equipment?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Follow the documented shutdown steps."
    assert body["ai_status"] == "success"
    assert body["sources"] == [{"document": "OSHA3120.pdf", "page": 12}]
    assert body["model_used"] == "configured-test-model"
    assert body["retry_count"] == 0
    assert body["prompt_tokens"] == 100
    assert body["completion_tokens"] == 50
    assert body["estimated_cost_usd"] is None
    assert all(
        body[name] >= 0
        for name in ("retrieval_ms", "generation_ms", "total_ms")
    )


@pytest.mark.parametrize("question", ["", "   "])
def test_chat_rejects_empty_question(client, question):
    response = client.post("/chat", json={"question": question})

    assert response.status_code == 422


def test_chat_uses_retrieved_passages_for_generation(
    client, monkeypatch, retrieved_passage
):
    captured_prompts = []
    monkeypatch.setattr(
        main, "search", lambda question, top_k: ([retrieved_passage], {})
    )

    def generate(prompt, deadline_ms):
        captured_prompts.append(prompt)
        return _generation("A grounded response.")

    monkeypatch.setattr(main, "generate_text_with_usage", generate)

    response = client.post("/chat", json={"question": "How do I prepare?"})

    assert response.status_code == 200
    assert "The employer shall prepare for shutdown" in captured_prompts[0]
    assert "OSHA3120.pdf" in captured_prompts[0]
    assert "Page: 12" in captured_prompts[0]


def test_chat_handles_gemini_unavailable_safely(
    client, monkeypatch, retrieved_passage
):
    monkeypatch.setattr(
        main, "search", lambda question, top_k: ([retrieved_passage], {})
    )

    def fail_generation(prompt, deadline_ms):
        raise RuntimeError("Gemini is not configured")

    monkeypatch.setattr(main, "generate_text_with_usage", fail_generation)

    response = client.post("/chat", json={"question": "How do I prepare?"})

    assert response.status_code == 200
    body = response.json()
    assert body["ai_status"] == "unavailable"
    assert "cannot provide a reliable synthesized answer" in body["answer"]
    assert "approved safety procedures" in body["answer"]
    assert body["sources"] == [{"document": "OSHA3120.pdf", "page": 12}]
    assert body["model_used"] is None


def test_chat_returns_cited_safe_fallback_for_gemini_503(
    client, monkeypatch, retrieved_passage
):
    class ServiceUnavailable(Exception):
        code = 503

    class FailingModels:
        def generate_content(self, *, model, contents):
            raise ServiceUnavailable("temporarily unavailable")

    class FakeClient:
        models = FailingModels()

        def close(self):
            pass

    settings = Settings(
        _env_file=None,
        gemini_api_key="not-a-real-key",
        gemini_model="configured-test-model",
        gemini_max_retries=0,
    )
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(llm, "get_settings", lambda: settings)
    monkeypatch.setattr(llm, "_create_client", lambda api_key, timeout_ms: FakeClient())
    monkeypatch.setattr(main, "search", lambda question, top_k: ([retrieved_passage], {}))

    response = client.post("/chat", json={"question": "How do I prepare?"})

    assert response.status_code == 200
    body = response.json()
    assert body["ai_status"] == "unavailable"
    assert body["model_used"] == "configured-test-model"
    assert body["retry_count"] == 0
    assert "cannot provide a reliable synthesized answer" in body["answer"]
    assert "approved safety procedures" in body["answer"]
    assert body["sources"] == [{"document": "OSHA3120.pdf", "page": 12}]


def test_chat_returns_safe_fallback_when_gemini_deadline_expires(
    client, monkeypatch, retrieved_passage
):
    monkeypatch.setattr(
        main, "search", lambda question, top_k: ([retrieved_passage], {})
    )

    def exceed_deadline(prompt, deadline_ms):
        raise GeminiDeadlineExceeded("deadline exceeded", retry_count=1)

    monkeypatch.setattr(main, "generate_text_with_usage", exceed_deadline)

    response = client.post("/chat", json={"question": "How do I prepare?"})

    assert response.status_code == 200
    body = response.json()
    assert body["ai_status"] == "unavailable"
    assert body["retry_count"] == 1
    assert "cannot provide a reliable synthesized answer" in body["answer"]
    assert body["sources"] == [{"document": "OSHA3120.pdf", "page": 12}]


def test_chat_returns_safe_response_when_no_documents_match(client, monkeypatch):
    generation_calls = []
    monkeypatch.setattr(main, "search", lambda question, top_k: ([], {}))
    monkeypatch.setattr(
        main,
        "generate_text_with_usage",
        lambda prompt, deadline_ms: generation_calls.append(prompt),
    )

    response = client.post(
        "/chat",
        json={"question": "How should I handle a chemical spill?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ai_status"] == "not_used"
    assert body["sources"] == []
    assert "do not provide relevant passages" in body["answer"]
    assert "approved safety procedures" in body["answer"]
    assert generation_calls == []


def test_chat_deduplicates_document_page_citations(
    client, monkeypatch, retrieved_passage
):
    duplicate_passage = (
        2,
        {
            **retrieved_passage[1],
            "chunk_id": 2,
            "text": "A second matching passage.",
        },
    )
    monkeypatch.setattr(
        main,
        "search",
        lambda question, top_k: ([retrieved_passage, duplicate_passage], {}),
    )
    monkeypatch.setattr(
        main,
        "generate_text_with_usage",
        lambda prompt, deadline_ms: _generation("A grounded response."),
    )

    response = client.post("/chat", json={"question": "How do I prepare?"})

    assert response.status_code == 200
    assert response.json()["sources"] == [{"document": "OSHA3120.pdf", "page": 12}]


def test_chat_handles_retrieval_error_with_safe_response(client, monkeypatch):
    monkeypatch.setattr(
        main, "search", lambda question, top_k: (_ for _ in ()).throw(OSError())
    )

    response = client.post("/chat", json={"question": "How do I prepare?"})

    assert response.status_code == 200
    assert response.json()["ai_status"] == "retrieval_error"
    assert response.json()["sources"] == []
    assert "approved safety procedures" in response.json()["answer"]


def test_stream_includes_citations_and_safe_fallback(
    client, monkeypatch, retrieved_passage
):
    class FailedStream:
        emitted_output = False
        model_used = None
        retry_count = 0
        prompt_tokens = None
        completion_tokens = None

        def __iter__(self):
            raise RuntimeError("stream is unavailable")

    monkeypatch.setattr(
        main, "search", lambda question, top_k: ([retrieved_passage], {})
    )
    monkeypatch.setattr(
        main,
        "generate_text_stream_with_usage",
        lambda prompt, deadline_ms: FailedStream(),
    )

    response = client.post("/chat/stream", json={"question": "How do I prepare?"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    metadata = _sse_payloads(response.text, "metadata")[0]
    assert metadata["sources"] == [{"document": "OSHA3120.pdf", "page": 12}]
    fallback = _sse_payloads(response.text, "fallback")[0]
    assert "approved safety procedures" in fallback["answer"]
    complete = _sse_payloads(response.text, "complete")[0]
    assert complete["ai_status"] == "unavailable"


def test_stream_success_includes_tokens_sources_and_completion_metadata(
    client, monkeypatch, retrieved_passage
):
    class SuccessfulStream:
        emitted_output = False
        model_used = "configured-test-model"
        retry_count = 1
        prompt_tokens = 20
        completion_tokens = 10

        def __iter__(self):
            self.emitted_output = True
            yield "grounded "
            yield "answer"

    monkeypatch.setattr(
        main, "search", lambda question, top_k: ([retrieved_passage], {})
    )
    monkeypatch.setattr(
        main,
        "generate_text_stream_with_usage",
        lambda prompt, deadline_ms: SuccessfulStream(),
    )

    response = client.post("/chat/stream", json={"question": "How do I prepare?"})

    assert response.status_code == 200
    assert [item["text"] for item in _sse_payloads(response.text, "token")] == [
        "grounded ",
        "answer",
    ]
    complete = _sse_payloads(response.text, "complete")[0]
    assert complete["ai_status"] == "success"
    assert complete["sources"] == [{"document": "OSHA3120.pdf", "page": 12}]
    assert complete["model_used"] == "configured-test-model"
    assert complete["retry_count"] == 1
    assert complete["prompt_tokens"] == 20
    assert complete["completion_tokens"] == 10


def test_stream_failure_after_output_is_not_replayed(
    client, monkeypatch, retrieved_passage
):
    class PartialStream:
        emitted_output = False
        model_used = "configured-test-model"
        retry_count = 0
        prompt_tokens = None
        completion_tokens = None

        def __iter__(self):
            self.emitted_output = True
            yield "partial answer"
            raise RuntimeError("connection dropped")

    monkeypatch.setattr(
        main, "search", lambda question, top_k: ([retrieved_passage], {})
    )
    monkeypatch.setattr(
        main,
        "generate_text_stream_with_usage",
        lambda prompt, deadline_ms: PartialStream(),
    )

    response = client.post("/chat/stream", json={"question": "How do I prepare?"})

    assert response.status_code == 200
    assert len(_sse_payloads(response.text, "token")) == 1
    assert "event: fallback" not in response.text
    assert _sse_payloads(response.text, "complete")[0]["ai_status"] == "partial"
    assert "Do not rely on partial text" in _sse_payloads(response.text, "warning")[0][
        "message"
    ]


def test_usage_endpoint_reports_tokens_retries_models_and_estimated_cost(
    client, monkeypatch, retrieved_passage
):
    monkeypatch.setattr(main, "usage_tracker", UsageTracker())
    monkeypatch.setattr(
        main,
        "get_settings",
        lambda: Settings(
            gemini_input_cost_per_million_usd=1.0,
            gemini_output_cost_per_million_usd=2.0,
        ),
    )
    monkeypatch.setattr(
        main, "search", lambda question, top_k: ([retrieved_passage], {})
    )
    monkeypatch.setattr(
        main,
        "generate_text_with_usage",
        lambda prompt, deadline_ms: _generation("A grounded response."),
    )

    chat_response = client.post("/chat", json={"question": "How do I prepare?"})
    usage_response = client.get("/usage")

    assert chat_response.status_code == 200
    assert chat_response.json()["estimated_cost_usd"] == pytest.approx(0.0002)
    assert usage_response.status_code == 200
    body = usage_response.json()
    assert body["total_requests"] == 1
    assert body["generation_requests"] == 1
    assert body["requests_by_status"] == {"success": 1}
    assert body["retry_count"] == 0
    assert body["prompt_tokens"] == 100
    assert body["completion_tokens"] == 50
    assert body["total_tokens"] == 150
    assert body["estimated_cost_usd"] == pytest.approx(0.0002)
    assert body["by_model"]["configured-test-model"]["requests"] == 1
