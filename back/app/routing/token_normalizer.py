"""LLM-фильтр токенов: оставляет только отклонения от нормы → жалобы/фичи."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from . import features as feat
from .vectorize import split_complaint_tokens

SYSTEM_PROMPT = """Ты клинический нормализатор токенов жалоб.
На входе: сырые текстовые фрагменты (жалобы, виталы, фразы из эпикриза) и каталог feature id.
Верни ТОЛЬКО JSON:
{
  "symptoms": string[],          // только реальные жалобы/отклонения, коротко
  "red_flags": string[],         // red flags, если явно есть отклонение/подозрение
  "active_features": string[],   // subset id из каталога (только подтверждённые отклонения)
  "dropped": [{"token": string, "reason": string}]  // что отброшено и почему
}

Правила:
- НЕ активируй симптом, если в токене сказано «в норме», «нормальный», «нет», «отрицает»,
  «без», «отсутствует», «не беспокоит», «не предъявляет» и т.п.
- Пример: «сердцебиение в норме» → dropped, НЕ symptom_palpitations.
- Пример: «одышки нет» → dropped.
- Пример: «жалобы: сердцебиение» / «сердцебиение» → symptoms + symptom_palpitations.
- Не выдумывай фичи вне каталога. active_features — только id из переданного списка.
- Если сомнение и нет явного отклонения — лучше drop.
- Ответ строго JSON без markdown.
"""


def _llm_client():
    from openai import OpenAI

    if os.getenv("OPENROUTER_API_KEY"):
        return OpenAI(
            api_key=os.environ["OPENROUTER_API_KEY"],
            base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            default_headers={
                "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "http://localhost:5173"),
                "X-Title": os.getenv("OPENROUTER_APP_NAME", "Sparrow Route"),
            },
            timeout=float(os.getenv("LLM_TIMEOUT_SEC", "90")),
        ), os.getenv("OPENROUTER_MODEL", "openrouter/free")
    if os.getenv("DEEPSEEK_API_KEY"):
        return OpenAI(
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            timeout=float(os.getenv("LLM_TIMEOUT_SEC", "90")),
        ), os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    if os.getenv("OPENAI_API_KEY"):
        return OpenAI(
            api_key=os.environ["OPENAI_API_KEY"],
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            timeout=float(os.getenv("LLM_TIMEOUT_SEC", "90")),
        ), os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    return None, None


def llm_configured() -> bool:
    return bool(
        os.getenv("OPENROUTER_API_KEY")
        or os.getenv("DEEPSEEK_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    if not text.startswith("{"):
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            raise ValueError("no json object")
        text = m.group(0)
    return json.loads(text)


def _message_text(message: Any) -> str:
    if message is None:
        return ""
    content = getattr(message, "content", None)
    if isinstance(content, str) and content.strip():
        return content
    for attr in ("reasoning", "reasoning_content"):
        val = getattr(message, attr, None)
        if isinstance(val, str) and val.strip():
            return val
    return ""


def collect_text_tokens(
    documents: list[Any] | None = None,
    *,
    extra_text: str = "",
    important: dict[str, Any] | None = None,
) -> list[str]:
    """Собрать сырые токены из документов / important / free text (без LLM)."""
    chunks: list[str] = []
    for doc in documents or []:
        if hasattr(doc, "model_dump"):
            d = doc.model_dump()
        else:
            d = doc if isinstance(doc, dict) else {}
        imp = d.get("important") or {}
        if hasattr(imp, "model_dump"):
            imp = imp.model_dump()
        for key in ("symptoms", "diagnoses", "red_flags", "clinical_snippets"):
            for item in imp.get(key) or []:
                chunks.append(str(item))
        raw = (d.get("raw_text") or "").strip()
        if raw:
            chunks.append(raw)
        if d.get("summary"):
            chunks.append(str(d["summary"]))

    if important:
        for key in ("symptoms", "diagnoses", "red_flags", "clinical_snippets", "free_text"):
            for item in important.get(key) or []:
                chunks.append(str(item))
        if important.get("text"):
            chunks.append(str(important["text"]))

    if extra_text and str(extra_text).strip():
        chunks.append(str(extra_text).strip())

    tokens: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        for t in split_complaint_tokens(chunk):
            k = re.sub(r"\s+", " ", t.lower().replace("ё", "е")).strip()
            if k in seen:
                continue
            seen.add(k)
            tokens.append(t)
    return tokens


def normalize_tokens(
    tokens: list[str],
    *,
    context: str = "",
) -> dict[str, Any]:
    """
    LLM: отфильтровать токены без отклонений, привести к symptoms + feature ids.
    Fallback без ключа/ошибки: source=passthrough (вызывающий код решит сам).
    """
    clean_tokens = [t for t in (tokens or []) if str(t).strip()]
    empty = {
        "symptoms": [],
        "red_flags": [],
        "active_features": [],
        "dropped": [],
        "text_tokens": clean_tokens,
        "source": "empty",
        "model": None,
    }
    if not clean_tokens and not (context or "").strip():
        return empty

    client, model = _llm_client()
    if client is None:
        return {
            **empty,
            "source": "no_api_key",
            "text_tokens": clean_tokens,
        }

    catalog = [{"id": f["id"], "label": f.get("label")} for f in feat.feature_meta()]
    user_payload = {
        "tokens": clean_tokens[:80],
        "context_excerpt": (context or "")[:4000],
        "feature_catalog": catalog,
    }

    from ..llm_retry import with_retries

    def _once() -> dict[str, Any]:
        completion = client.chat.completions.create(
            model=model,
            temperature=0,
            max_tokens=int(os.getenv("STRUCTURE_MAX_TOKENS", "2048")),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": "Отфильтруй токены (только отклонения) и верни JSON:\n"
                    + json.dumps(user_payload, ensure_ascii=False),
                },
            ],
        )
        choices = getattr(completion, "choices", None)
        if not choices:
            raise RuntimeError("empty choices")
        raw = _message_text(choices[0].message)
        if not (raw or "").strip():
            raise RuntimeError("пустой content")
        payload = _extract_json(raw)

        allowed = set(feat.feature_ids())
        active = [fid for fid in (payload.get("active_features") or []) if fid in allowed]
        symptoms = [str(s).strip() for s in (payload.get("symptoms") or []) if str(s).strip()]
        red_flags = [str(s).strip() for s in (payload.get("red_flags") or []) if str(s).strip()]
        dropped = []
        for item in payload.get("dropped") or []:
            if isinstance(item, dict):
                dropped.append(
                    {
                        "token": str(item.get("token") or ""),
                        "reason": str(item.get("reason") or ""),
                    }
                )

        return {
            "symptoms": symptoms,
            "red_flags": red_flags,
            "active_features": active,
            "dropped": dropped,
            "text_tokens": clean_tokens,
            "source": "llm",
            "model": getattr(completion, "model", None) or model,
        }

    try:
        return with_retries(_once, label="tokenize")
    except Exception as exc:  # noqa: BLE001
        return {
            **empty,
            "source": f"llm_error:{exc}",
            "text_tokens": clean_tokens,
        }
