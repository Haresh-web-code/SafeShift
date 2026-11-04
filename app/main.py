import json
import logging
import time
from typing import Annotated, Any

from fastapi import Depends, FastAPI
from fastapi.responses import StreamingResponse

from app.config import Settings, get_settings
from app.llm import (
    generate_text_stream_with_usage,
    generate_text_with_usage,
)
from app.schemas import ChatRequest, ChatResponse, Source, UsageResponse
from app.usage import usage_tracker
from tools.search import search

app = FastAPI(title="SafeShift", version="0.2.0")

SettingsDep = Annotated[Settings, Depends(get_settings)]
logger = logging.getLogger(__name__)
RESPONSE_BUDGET_MS = 2_000
SAFE_UNAVAILABLE_ANSWER = (
    "Gemini is unavailable, so I cannot provide a reliable synthesized answer. "
    "Review the cited OSHA passages and follow your approved safety procedures "
    "and site procedures."
)
SAFE_NO_SOURCES_ANSWER = (
    "The available OSHA documents do not provide relevant passages to support "
    "an answer. Follow your approved safety procedures and site procedures."
)
SAFE_RETRIEVAL_ERROR_ANSWER = (
    "OSHA document retrieval is temporarily unavailable. Follow your approved "
    "safety procedures and site procedures."
)
SAFE_PARTIAL_STREAM_WARNING = (
    "Gemini stopped before the answer was complete. Do not rely on partial text; "
    "review the cited OSHA sources and follow your approved safety procedures."
)


def build_prompt(question: str, results: list) -> str:
    passages = []
    for _, chunk in results:
        passages.append(
            f"Document: {chunk['document']}\n"
            f"Page: {chunk['page']}\n"
            f"Passage:\n{chunk['text']}"
        )

    retrieved_passages = "\n\n".join(passages)
    return f"""You are SafeShift, an assistant for workplace safety questions.

Answer the supervisor's question using only the OSHA passages below.
Do not invent requirements, procedures, or citations.
If the passages do not adequately support an answer, clearly say so.
Cite only the document and page references provided.
Refer the supervisor to approved site procedures.

Supervisor question:
{question}

Retrieved OSHA passages:
{retrieved_passages}
"""


def get_sources(results: list) -> list[Source]:
    sources = []
    seen_sources = set()
    for _, chunk in results:
        source_key = (chunk["document"], chunk["page"])
        if source_key not in seen_sources:
            sources.append(Source(document=source_key[0], page=source_key[1]))
            seen_sources.add(source_key)
    return sources


def _estimated_cost(
    prompt_tokens: int | None,
    completion_tokens: int | None,
    settings: Settings,
) -> float | None:
    if (
        prompt_tokens is None
        or completion_tokens is None
        or settings.gemini_input_cost_per_million_usd is None
        or settings.gemini_output_cost_per_million_usd is None
    ):
        return None

    return (
        prompt_tokens * settings.gemini_input_cost_per_million_usd
        + completion_tokens * settings.gemini_output_cost_per_million_usd
    ) / 1_000_000


def _record_request(
    *,
    ai_status: str,
    generation_attempted: bool,
    model_used: str | None,
    retry_count: int,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    settings: Settings,
) -> float | None:
    estimated_cost = _estimated_cost(prompt_tokens, completion_tokens, settings)
    usage_tracker.record(
        ai_status=ai_status,
        generation_attempted=generation_attempted,
        model_used=model_used,
        retry_count=retry_count,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        estimated_cost_usd=estimated_cost,
    )
    return estimated_cost


def _log_request(
    *,
    retrieval_ms: float,
    generation_ms: float,
    total_ms: float,
    retry_count: int,
    model_used: str | None,
    ai_status: str,
) -> None:
    logger.info(
        "chat completed retrieval_ms=%.2f generation_ms=%.2f total_ms=%.2f "
        "retry_count=%d model_used=%s ai_status=%s",
        retrieval_ms,
        generation_ms,
        total_ms,
        retry_count,
        model_used or "none",
        ai_status,
    )


def _remaining_budget_ms(total_start: float, settings: Settings) -> int:
    elapsed_ms = (time.perf_counter() - total_start) * 1000
    return max(0, min(settings.gemini_deadline_ms, int(RESPONSE_BUDGET_MS - elapsed_ms)))


def _sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


@app.get("/health")
def health(settings: SettingsDep) -> dict:
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.environment,
    }


@app.get("/usage", response_model=UsageResponse)
def usage() -> dict:
    return usage_tracker.snapshot()


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    total_start = time.perf_counter()
    settings = get_settings()
    retrieval_start = time.perf_counter()

    try:
        results, _ = search(request.question, top_k=5)
    except Exception as error:
        retrieval_ms = (time.perf_counter() - retrieval_start) * 1000
        total_ms = (time.perf_counter() - total_start) * 1000
        logger.error("OSHA retrieval failed error_type=%s", type(error).__name__)
        _record_request(
            ai_status="retrieval_error",
            generation_attempted=False,
            model_used=None,
            retry_count=0,
            prompt_tokens=None,
            completion_tokens=None,
            settings=settings,
        )
        _log_request(
            retrieval_ms=retrieval_ms,
            generation_ms=0,
            total_ms=total_ms,
            retry_count=0,
            model_used=None,
            ai_status="retrieval_error",
        )
        return ChatResponse(
            answer=SAFE_RETRIEVAL_ERROR_ANSWER,
            sources=[],
            ai_status="retrieval_error",
            retrieval_ms=retrieval_ms,
            generation_ms=0,
            total_ms=total_ms,
        )

    retrieval_ms = (time.perf_counter() - retrieval_start) * 1000
    if not results:
        total_ms = (time.perf_counter() - total_start) * 1000
        _record_request(
            ai_status="not_used",
            generation_attempted=False,
            model_used=None,
            retry_count=0,
            prompt_tokens=None,
            completion_tokens=None,
            settings=settings,
        )
        _log_request(
            retrieval_ms=retrieval_ms,
            generation_ms=0,
            total_ms=total_ms,
            retry_count=0,
            model_used=None,
            ai_status="not_used",
        )
        return ChatResponse(
            answer=SAFE_NO_SOURCES_ANSWER,
            sources=[],
            ai_status="not_used",
            retrieval_ms=retrieval_ms,
            generation_ms=0,
            total_ms=total_ms,
        )

    sources = get_sources(results)
    prompt = build_prompt(request.question, results)
    generation_start = time.perf_counter()
    generation = None
    error: Exception | None = None
    try:
        generation = generate_text_with_usage(
            prompt,
            deadline_ms=_remaining_budget_ms(total_start, settings),
        )
        answer = generation.text
        ai_status = "success"
    except Exception as exc:
        error = exc
        answer = SAFE_UNAVAILABLE_ANSWER
        ai_status = "unavailable"
        logger.warning("Gemini generation failed error_type=%s", type(exc).__name__)

    generation_ms = (time.perf_counter() - generation_start) * 1000
    model_used = (
        generation.model_used
        if generation is not None
        else getattr(error, "model_used", None)
    )
    retry_count = (
        generation.retry_count
        if generation is not None
        else getattr(error, "retry_count", 0)
    )
    prompt_tokens = generation.prompt_tokens if generation is not None else None
    completion_tokens = generation.completion_tokens if generation is not None else None
    estimated_cost = _record_request(
        ai_status=ai_status,
        generation_attempted=True,
        model_used=model_used,
        retry_count=retry_count,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        settings=settings,
    )
    total_ms = (time.perf_counter() - total_start) * 1000
    _log_request(
        retrieval_ms=retrieval_ms,
        generation_ms=generation_ms,
        total_ms=total_ms,
        retry_count=retry_count,
        model_used=model_used,
        ai_status=ai_status,
    )

    return ChatResponse(
        answer=answer,
        sources=sources,
        ai_status=ai_status,
        retrieval_ms=retrieval_ms,
        generation_ms=generation_ms,
        total_ms=total_ms,
        model_used=model_used,
        retry_count=retry_count,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        estimated_cost_usd=estimated_cost,
    )


@app.post("/chat/stream")
def chat_stream(request: ChatRequest) -> StreamingResponse:
    total_start = time.perf_counter()
    settings = get_settings()
    retrieval_start = time.perf_counter()
    retrieval_error: Exception | None = None

    try:
        results, _ = search(request.question, top_k=5)
    except Exception as error:
        results = []
        retrieval_error = error

    retrieval_ms = (time.perf_counter() - retrieval_start) * 1000
    sources = get_sources(results)
    prompt = build_prompt(request.question, results) if results else ""

    def response_generator() -> Any:
        yield _sse(
            "metadata",
            {
                "sources": [source.model_dump() for source in sources],
                "retrieval_ms": retrieval_ms,
                "ai_status": "pending",
            },
        )

        model_used: str | None = None
        retry_count = 0
        prompt_tokens = None
        completion_tokens = None
        generation_attempted = False
        generation_start = time.perf_counter()

        if retrieval_error is not None:
            ai_status = "retrieval_error"
            answer = SAFE_RETRIEVAL_ERROR_ANSWER
            logger.error(
                "OSHA retrieval failed error_type=%s",
                type(retrieval_error).__name__,
            )
            yield _sse("fallback", {"answer": answer})
        elif not results:
            ai_status = "not_used"
            answer = SAFE_NO_SOURCES_ANSWER
            yield _sse("fallback", {"answer": answer})
        else:
            generation_attempted = True
            stream = generate_text_stream_with_usage(
                prompt,
                deadline_ms=_remaining_budget_ms(total_start, settings),
            )
            try:
                for text in stream:
                    yield _sse("token", {"text": text})
                ai_status = "success"
            except Exception as error:
                ai_status = "partial" if stream.emitted_output else "unavailable"
                logger.warning(
                    "Gemini stream failed error_type=%s partial=%s",
                    type(error).__name__,
                    stream.emitted_output,
                )
                if stream.emitted_output:
                    yield _sse("warning", {"message": SAFE_PARTIAL_STREAM_WARNING})
                else:
                    yield _sse("fallback", {"answer": SAFE_UNAVAILABLE_ANSWER})

            model_used = stream.model_used
            retry_count = stream.retry_count
            prompt_tokens = stream.prompt_tokens
            completion_tokens = stream.completion_tokens

        generation_ms = (
            (time.perf_counter() - generation_start) * 1000
            if generation_attempted
            else 0
        )
        estimated_cost = _record_request(
            ai_status=ai_status,
            generation_attempted=generation_attempted,
            model_used=model_used,
            retry_count=retry_count,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            settings=settings,
        )
        total_ms = (time.perf_counter() - total_start) * 1000
        _log_request(
            retrieval_ms=retrieval_ms,
            generation_ms=generation_ms,
            total_ms=total_ms,
            retry_count=retry_count,
            model_used=model_used,
            ai_status=ai_status,
        )
        yield _sse(
            "complete",
            {
                "sources": [source.model_dump() for source in sources],
                "ai_status": ai_status,
                "retrieval_ms": retrieval_ms,
                "generation_ms": generation_ms,
                "total_ms": total_ms,
                "model_used": model_used,
                "retry_count": retry_count,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "estimated_cost_usd": estimated_cost,
            },
        )

    return StreamingResponse(
        response_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
