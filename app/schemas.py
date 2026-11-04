from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        question = value.strip()
        if not question:
            raise ValueError("Question must not be empty.")
        return question


class Source(BaseModel):
    document: str
    page: int


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
    ai_status: Literal[
        "success",
        "unavailable",
        "not_used",
        "retrieval_error",
        "partial",
    ]
    retrieval_ms: float
    generation_ms: float
    total_ms: float
    model_used: str | None = None
    retry_count: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    estimated_cost_usd: float | None = None


class ModelUsage(BaseModel):
    requests: int
    retry_count: int
    prompt_tokens: int
    completion_tokens: int


class UsageResponse(BaseModel):
    total_requests: int
    generation_requests: int
    requests_by_status: dict[str, int]
    retry_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float | None
    by_model: dict[str, ModelUsage]
