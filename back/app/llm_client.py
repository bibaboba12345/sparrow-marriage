"""Shared LLM client resolution (Cloud.ru / Amvera / OpenRouter / DeepSeek / OpenAI)."""

from __future__ import annotations

import os
from typing import Any


def _amvera_key() -> str | None:
    return (
        os.getenv("AMVERACLOUD_API_KEY")
        or os.getenv("AMVERA_API_KEY")
        or os.getenv("AMVERA_API_TOKEN")
    )


def _cloudru_key() -> str | None:
    return (
        os.getenv("CLOUDRU_API_KEY")
        or os.getenv("CLOUD_RU_API_KEY")
        or os.getenv("FOUNDATION_MODELS_API_KEY")
    )


def resolve_llm() -> tuple[str, str, str]:
    """Returns (api_key, base_url, model).

    Priority: Cloud.ru → Amvera → OpenRouter → DeepSeek → OpenAI.
    """
    cloudru = _cloudru_key()
    if cloudru:
        return (
            cloudru,
            os.getenv(
                "CLOUDRU_BASE_URL",
                os.getenv(
                    "FOUNDATION_MODELS_BASE_URL",
                    "https://foundation-models.api.cloud.ru/v1",
                ),
            ),
            os.getenv(
                "CLOUDRU_MODEL",
                os.getenv("FOUNDATION_MODELS_MODEL", "openai/gpt-oss-120b"),
            ),
        )
    amvera = _amvera_key()
    if amvera:
        return (
            amvera,
            os.getenv("AMVERACLOUD_BASE_URL", "https://inference.waw0.amvera.ru/v1"),
            os.getenv("AMVERACLOUD_MODEL", os.getenv("AMVERA_MODEL", "llama70b")),
        )
    if os.getenv("OPENROUTER_API_KEY"):
        return (
            os.environ["OPENROUTER_API_KEY"],
            os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            os.getenv("OPENROUTER_MODEL", "openrouter/free"),
        )
    if os.getenv("DEEPSEEK_API_KEY"):
        return (
            os.environ["DEEPSEEK_API_KEY"],
            os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        )
    if os.getenv("OPENAI_API_KEY"):
        return (
            os.environ["OPENAI_API_KEY"],
            os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        )
    raise RuntimeError(
        "Нет API-ключа. Добавь CLOUDRU_API_KEY / AMVERACLOUD_API_KEY / "
        "OPENROUTER_API_KEY / DEEPSEEK_API_KEY / OPENAI_API_KEY в back/.env"
    )


def llm_configured() -> bool:
    return bool(
        _cloudru_key()
        or _amvera_key()
        or os.getenv("OPENROUTER_API_KEY")
        or os.getenv("DEEPSEEK_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )


def provider_name() -> str:
    """Short provider id for logs / feature switches."""
    try:
        _, base, model = resolve_llm()
    except RuntimeError:
        return "none"
    if "cloud.ru" in base or model.startswith("openai/gpt-oss"):
        return "cloudru"
    if "amvera" in base:
        return "amvera"
    if "openrouter" in base:
        return "openrouter"
    if "deepseek" in base:
        return "deepseek"
    return "openai"


def chat_completion_kwargs(*, max_tokens: int | None = None, **extra: Any) -> dict[str, Any]:
    """Normalize completion kwargs across providers.

    Cloud.ru / gpt-oss prefer ``max_completion_tokens``; others use ``max_tokens``.
    """
    out = dict(extra)
    if max_tokens is None:
        return out
    if provider_name() == "cloudru":
        # Foundation Models docs use max_completion_tokens for newer models.
        out["max_completion_tokens"] = int(max_tokens)
        out.pop("max_tokens", None)
    else:
        out["max_tokens"] = int(max_tokens)
        out.pop("max_completion_tokens", None)
    return out


def make_openai_client(
    *,
    timeout: float | None = None,
    max_retries: int | None = None,
) -> tuple[Any, str]:
    """OpenAI-compatible client + model name for the configured provider."""
    from openai import OpenAI

    api_key, base_url, model = resolve_llm()
    default_headers: dict[str, str] | None = None
    if "openrouter.ai" in base_url:
        default_headers = {
            "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "http://localhost:5173"),
            "X-Title": os.getenv("OPENROUTER_APP_NAME", "Sparrow Route"),
        }
    if timeout is None:
        timeout = float(os.getenv("LLM_TIMEOUT_SEC", "120"))
    if max_retries is None:
        max_retries = int(os.getenv("LLM_HTTP_MAX_RETRIES", "2"))
    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        default_headers=default_headers,
        timeout=timeout,
        max_retries=max_retries,
    )
    return client, model
