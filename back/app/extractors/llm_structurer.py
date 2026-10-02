"""LLM-структуризатор текста документа → StructuredDocument (OpenRouter / DeepSeek / OpenAI)."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from .structure_schema import StructuredDocument

SYSTEM_PROMPT = """Ты медицинский парсер выписок и лабораторных бланков.
Из сырого текста документа верни ТОЛЬКО JSON по схеме:

{
  "important": {
    "patient_name": string|null,
    "age": number|null,
    "sex": string|null,
    "symptoms": string[],
    "diagnoses": string[],
    "labs": [{"name": string, "value": string, "unit": string|null, "ref_range": string|null}],
    "medications": string[],
    "vitals": {string: string},
    "red_flags": string[],
    "clinical_snippets": string[]
  },
  "metadata_junk": {
    "headers_footers": string[],
    "clinic_meta": string[],
    "document_ids": string[],
    "legalese": string[],
    "other_noise": string[]
  },
  "summary": string
}

Правила:
- В important — только клинически полезное для маршрутизации пациента.
- В metadata_junk — шапки, адреса клиник, печати, штрихкоды, дисклеймеры, «страница N из M».
- Не выдумывай анализы и диагнозы, которых нет в тексте.
- labs[].value всегда строка (даже если число).
- clinical_snippets — короткие дословные цитаты.
- summary — 1–3 предложения по-русски.
- Ответ строго JSON, без markdown.
"""


class StructureError(Exception):
    pass


def _resolve_llm() -> tuple[str, str, str]:
    """Returns (api_key, base_url, model). Priority: OPENROUTER → DEEPSEEK → OPENAI."""
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
    raise StructureError(
        "Нет API-ключа. Добавь OPENROUTER_API_KEY / DEEPSEEK_API_KEY / OPENAI_API_KEY в back/.env"
    )


def llm_configured() -> bool:
    return bool(
        os.getenv("OPENROUTER_API_KEY")
        or os.getenv("DEEPSEEK_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )


def _message_text(message: Any) -> str:
    """Достать текст из content / reasoning (free reasoning-модели часто кладут JSON туда)."""
    if message is None:
        return ""
    content = getattr(message, "content", None)
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text") or "")
            else:
                text = getattr(block, "text", None)
                if text:
                    parts.append(text)
        joined = "\n".join(parts).strip()
        if joined:
            return joined

    for attr in ("reasoning", "reasoning_content"):
        val = getattr(message, attr, None)
        if isinstance(val, str) and val.strip():
            return val

    # model_extra / dict fallback
    extra = getattr(message, "model_extra", None) or {}
    if isinstance(extra, dict):
        for key in ("reasoning", "reasoning_content"):
            val = extra.get(key)
            if isinstance(val, str) and val.strip():
                return val
    return ""


def _extract_json_blob(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    if text.startswith("{"):
        return text
    match = re.search(r"\{[\s\S]*\}", text)
    return match.group(0) if match else text


def _coerce_lab_values(payload: dict[str, Any]) -> dict[str, Any]:
    """LLM часто отдаёт value числом — приводим к str для схемы."""
    important = payload.get("important")
    if not isinstance(important, dict):
        return payload
    labs = important.get("labs")
    if not isinstance(labs, list):
        return payload
    fixed = []
    for lab in labs:
        if not isinstance(lab, dict):
            continue
        item = dict(lab)
        if "value" in item and item["value"] is not None and not isinstance(item["value"], str):
            item["value"] = str(item["value"])
        fixed.append(item)
    important = dict(important)
    important["labs"] = fixed
    payload = dict(payload)
    payload["important"] = important
    return payload


def structure_text(raw_text: str, *, filename: str | None = None) -> StructuredDocument:
    if not raw_text or not raw_text.strip():
        raise StructureError("Empty text for structuring")

    api_key, base_url, model = _resolve_llm()

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise StructureError("Пакет openai не установлен (pip install openai)") from exc

    from ..llm_retry import with_retries

    default_headers = {}
    if "openrouter.ai" in base_url:
        default_headers = {
            "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "http://localhost:5173"),
            "X-Title": os.getenv("OPENROUTER_APP_NAME", "Sparrow Route"),
        }

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        default_headers=default_headers or None,
        timeout=float(os.getenv("LLM_TIMEOUT_SEC", "120")),
    )
    user_blob = raw_text.strip()
    if filename:
        user_blob = f"Файл: {filename}\n\n{user_blob}"
    max_chars = int(os.getenv("STRUCTURE_MAX_CHARS", "12000"))
    if len(user_blob) > max_chars:
        user_blob = user_blob[:max_chars] + "\n\n[... truncated ...]"

    kwargs: dict[str, Any] = {
        "model": model,
        "temperature": 0.1,
        "max_tokens": int(os.getenv("STRUCTURE_MAX_TOKENS", "2048")),
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Разбери документ в JSON:\n\n{user_blob}"},
        ],
    }

    def _once() -> Any:
        try:
            completion = client.chat.completions.create(
                **kwargs,
                response_format={"type": "json_object"},
            )
        except Exception as first_exc:
            msg = str(first_exc).lower()
            if "timeout" in msg or "timed out" in msg:
                raise StructureError(
                    f"LLM timeout ({os.getenv('LLM_TIMEOUT_SEC', '120')}s). Free OpenRouter model hung."
                ) from first_exc
            # json_object not supported → retry without format once inside attempt
            try:
                completion = client.chat.completions.create(**kwargs)
            except Exception as exc:  # noqa: BLE001
                raise StructureError(f"LLM request failed: {exc}") from exc

        choices = getattr(completion, "choices", None)
        if not choices:
            raise StructureError(
                f"LLM вернула пустой choices (model={getattr(completion, 'model', model)}). "
                "Free OpenRouter иногда так делает — повтори запрос."
            )

        message = choices[0].message
        content = _extract_json_blob(_message_text(message))
        if not content:
            raise StructureError(
                "LLM вернула пустой content/reasoning. "
                "Смени OPENROUTER_MODEL или повтори — free-модели часто отдают пустой ответ."
            )

        try:
            payload: dict[str, Any] = json.loads(content)
        except json.JSONDecodeError as exc:
            raise StructureError(f"LLM вернула не-JSON: {content[:400]}") from exc

        if not isinstance(payload, dict):
            raise StructureError(f"Ожидали JSON-object, получили {type(payload).__name__}")

        payload = _coerce_lab_values(payload)

        try:
            doc = StructuredDocument.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            raise StructureError(f"JSON не прошёл схему: {exc}") from exc

        doc.model = getattr(completion, "model", None) or model
        doc.raw_char_count = len(raw_text)
        return doc

    try:
        return with_retries(_once, label="structure")
    except StructureError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise StructureError(f"LLM request failed after retries: {exc}") from exc
