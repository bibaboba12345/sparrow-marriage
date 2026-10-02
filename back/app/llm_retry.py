"""Retry helper for flaky LLM / gateway responses."""

from __future__ import annotations

import os
import time
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def max_attempts() -> int:
    return max(1, int(os.getenv("LLM_RETRY_ATTEMPTS", "3")))


def _is_transient(exc: BaseException) -> bool:
    msg = str(exc).lower()
    needles = (
        "502",
        "503",
        "504",
        "429",
        "bad gateway",
        "gateway timeout",
        "service unavailable",
        "timeout",
        "timed out",
        "connection",
        "temporarily",
        "rate limit",
        "overloaded",
        "empty choices",
        "пустой choices",
        "пустой content",
    )
    if any(n in msg for n in needles):
        return True
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status in {408, 429, 500, 502, 503, 504}:
        return True
    body = getattr(exc, "body", None) or getattr(exc, "response", None)
    text = str(body).lower() if body is not None else ""
    return any(n in text for n in ("502", "503", "504", "429", "bad gateway"))


def with_retries(
    fn: Callable[[], T],
    *,
    attempts: int | None = None,
    label: str = "llm",
    retry_if: Callable[[BaseException], bool] | None = None,
) -> T:
    """Call fn up to N times on transient errors (502/timeout/empty…)."""
    n = attempts if attempts is not None else max_attempts()
    check = retry_if or _is_transient
    last: BaseException | None = None
    for i in range(n):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last = exc
            if i >= n - 1 or not check(exc):
                raise
            delay = float(os.getenv("LLM_RETRY_BASE_SEC", "1.5")) * (2**i)
            time.sleep(min(delay, 12.0))
    assert last is not None
    raise last


def sleep_backoff(attempt_index: int) -> None:
    delay = float(os.getenv("LLM_RETRY_BASE_SEC", "1.5")) * (2**attempt_index)
    time.sleep(min(delay, 12.0))
