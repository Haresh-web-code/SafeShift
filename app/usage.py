from collections import defaultdict
from threading import Lock
from typing import Any


class UsageTracker:
    def __init__(self) -> None:
        self._lock = Lock()
        self._requests = 0
        self._generation_requests = 0
        self._statuses: dict[str, int] = defaultdict(int)
        self._retry_count = 0
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._estimated_cost_usd = 0.0
        self._cost_is_complete = True
        self._models: dict[str, dict[str, int]] = defaultdict(
            lambda: {
                "requests": 0,
                "retry_count": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
            }
        )

    def record(
        self,
        *,
        ai_status: str,
        generation_attempted: bool,
        model_used: str | None,
        retry_count: int,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        estimated_cost_usd: float | None,
    ) -> None:
        with self._lock:
            self._requests += 1
            self._statuses[ai_status] += 1
            self._retry_count += retry_count

            if generation_attempted:
                self._generation_requests += 1
                if estimated_cost_usd is None:
                    self._cost_is_complete = False
                else:
                    self._estimated_cost_usd += estimated_cost_usd

            if prompt_tokens is not None:
                self._prompt_tokens += prompt_tokens
            if completion_tokens is not None:
                self._completion_tokens += completion_tokens

            if model_used is not None:
                model = self._models[model_used]
                model["requests"] += 1
                model["retry_count"] += retry_count
                model["prompt_tokens"] += prompt_tokens or 0
                model["completion_tokens"] += completion_tokens or 0

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "total_requests": self._requests,
                "generation_requests": self._generation_requests,
                "requests_by_status": dict(self._statuses),
                "retry_count": self._retry_count,
                "prompt_tokens": self._prompt_tokens,
                "completion_tokens": self._completion_tokens,
                "total_tokens": self._prompt_tokens + self._completion_tokens,
                "estimated_cost_usd": (
                    self._estimated_cost_usd
                    if self._generation_requests and self._cost_is_complete
                    else None
                ),
                "by_model": {
                    name: dict(values) for name, values in self._models.items()
                },
            }


usage_tracker = UsageTracker()
