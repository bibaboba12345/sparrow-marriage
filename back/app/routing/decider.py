"""Decider: nearest-case base + LLM structured routing (see DECIDER_SPEC.md)."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from .matcher import MatchResult, match_vector
from .token_normalizer import collect_text_tokens, normalize_tokens
from .vectorize import aggregate_important, vectorize_documents, vectorize_important

SYSTEM_PROMPT = """Ты клинический маршрутизатор пациентов (Decider).
Верни ТОЛЬКО JSON:
{
  "priority": "emergency" | "urgent" | "routine",
  "department": string,
  "specialists": string[],
  "required_tests": string[],
  "reasoning": string[]
}

Правила:
- Опирайся на nearest case как на базовый шаблон маршрута.
- Не выдумывай анализы/симптомы, которых нет во входных данных.
- При red flags (STEMI, сепсис, инсульт, анафилаксия, кровотечение) повышай срочность.
- reasoning: 2–5 пунктов; укажи matched case id и ключевые маркеры входа.
- Ответ строго JSON без markdown.
"""


def _llm_client():
    from ..llm_client import llm_configured, make_openai_client

    if not llm_configured():
        return None, None
    try:
        return make_openai_client(timeout=float(os.getenv("LLM_TIMEOUT_SEC", "120")))
    except Exception:
        return None, None


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


def _fallback_from_match(
    match: MatchResult,
    reason: str,
    tokens_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    routing = dict(match.case.get("routing") or {})
    reasoning = list(routing.get("reasoning") or [])
    reasoning.append(
        f"Decider fallback ({reason}); matched {match.case.get('id')} score={match.score}"
    )
    dj = {
        **match.to_dict(),
        "decider_model": None,
        "decider_source": "fallback",
        "fallback_reason": reason,
    }
    if tokens_summary:
        dj["text_tokens"] = tokens_summary.get("text_tokens") or []
        dj["matched_phrases"] = tokens_summary.get("matched_phrases") or []
        dj["token_filter"] = tokens_summary.get("token_filter") or {}
    return {
        "priority": routing.get("priority") or "routine",
        "department": routing.get("department") or "Терапия",
        "specialists": list(routing.get("specialists") or ["Терапевт"]),
        "required_tests": list(routing.get("required_tests") or []),
        "reasoning": reasoning,
        "decision_json": dj,
    }


def _decide_llm(match: MatchResult, epicrisis: str, tokens_summary: dict[str, Any]) -> dict[str, Any]:
    client, model = _llm_client()
    if client is None:
        return _fallback_from_match(match, "no_api_key", tokens_summary)

    user = {
        "epicrisis_excerpt": (epicrisis or "")[:6000],
        "query_tokens": tokens_summary,
        "match": {
            "case_id": match.case.get("id"),
            "title": match.case.get("title"),
            "score": match.score,
            "case_active": match.case_active,
            "query_active": match.query_active,
            "template_routing": match.case.get("routing"),
            "epicrisis_snippet": match.case.get("epicrisis_snippet"),
        },
    }
    try:
        from ..llm_retry import with_retries

        def _once() -> Any:
            from ..llm_client import chat_completion_kwargs

            completion = client.chat.completions.create(
                **chat_completion_kwargs(
                    max_tokens=int(os.getenv("STRUCTURE_MAX_TOKENS", "2048")),
                    model=model,
                    temperature=0.1,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": "Сформируй маршрут JSON по данным:\n"
                            + json.dumps(user, ensure_ascii=False),
                        },
                    ],
                )
            )
            choices = getattr(completion, "choices", None)
            if not choices:
                raise RuntimeError("empty choices")
            raw = _message_text(choices[0].message)
            if not (raw or "").strip():
                raise RuntimeError("пустой content")
            payload = _extract_json(raw)
            return completion, payload

        completion, payload = with_retries(_once, label="decider")
    except Exception as exc:  # noqa: BLE001
        return _fallback_from_match(match, f"llm_error:{exc}", tokens_summary)

    priority = payload.get("priority") or "routine"
    if priority not in {"emergency", "urgent", "routine"}:
        priority = "routine"

    return {
        "priority": priority,
        "department": payload.get("department") or match.case.get("routing", {}).get("department") or "Терапия",
        "specialists": list(payload.get("specialists") or []),
        "required_tests": list(payload.get("required_tests") or []),
        "reasoning": list(payload.get("reasoning") or []),
        "decision_json": {
            **match.to_dict(),
            "text_tokens": tokens_summary.get("text_tokens") or [],
            "matched_phrases": tokens_summary.get("matched_phrases") or [],
            "token_filter": tokens_summary.get("token_filter") or {},
            "decider_model": getattr(completion, "model", None) or model,
            "decider_source": "llm",
        },
    }


def _vectorize_with_token_llm(
    documents: list[Any] | None = None,
    *,
    raw_input: str = "",
    important: dict[str, Any] | None = None,
    use_llm_filter: bool = True,
) -> dict[str, Any]:
    """Токены → (LLM фильтр отклонений) → vectorize."""
    tokens = collect_text_tokens(documents, extra_text=raw_input, important=important)
    context = raw_input or ""
    if not context and documents:
        context = "\n\n".join(
            getattr(d, "raw_text", None)
            or (d.get("raw_text") if isinstance(d, dict) else "")
            or ""
            for d in documents
        )

    norm: dict[str, Any] | None = None
    if use_llm_filter and tokens:
        norm = normalize_tokens(tokens, context=context)

    if norm and norm.get("source") == "llm":
        base = aggregate_important(documents or [], extra_text=raw_input or "")
        if important:
            # merge explicit important over docs
            for key in ("symptoms", "diagnoses", "red_flags", "medications", "clinical_snippets"):
                base[key] = list(base.get(key) or []) + list(important.get(key) or [])
            for lab in important.get("labs") or []:
                base.setdefault("labs", []).append(lab)
            for k, v in (important.get("vitals") or {}).items():
                base.setdefault("vitals", {})[str(k)] = str(v)

        # Replace complaint streams with LLM-approved deviations only.
        base["symptoms"] = list(norm.get("symptoms") or [])
        base["red_flags"] = list(norm.get("red_flags") or [])
        base["clinical_snippets"] = []
        # Keep free_text for numeric vitals/labs extraction, but do not alias it.
        vec_info = vectorize_important(
            base,
            alias_free_text=False,
            seed_active=norm.get("active_features") or [],
        )
        vec_info["text_tokens"] = norm.get("text_tokens") or tokens
        vec_info["token_filter"] = {
            "source": norm.get("source"),
            "model": norm.get("model"),
            "dropped": norm.get("dropped") or [],
            "symptoms": norm.get("symptoms") or [],
            "red_flags": norm.get("red_flags") or [],
        }
        vec_info["matched_phrases"] = [
            {"token": s, "feature": fid}
            for s, fid in zip(
                norm.get("symptoms") or [],
                (norm.get("active_features") or [])[: len(norm.get("symptoms") or [])],
                strict=False,
            )
        ] or [
            {"token": fid, "feature": fid} for fid in (norm.get("active_features") or [])
        ]
        return vec_info

    # Fallback: heuristic aliases (в т.ч. без LLM-ключа)
    if documents:
        vec_info = vectorize_documents(documents, extra_text=raw_input or "")
    elif important:
        vec_info = vectorize_important(important)
    else:
        vec_info = vectorize_important({"text": raw_input, "free_text": [raw_input]} if raw_input else {})
    vec_info["token_filter"] = {
        "source": (norm or {}).get("source") or "heuristic",
        "model": (norm or {}).get("model"),
        "dropped": (norm or {}).get("dropped") or [],
        "symptoms": [],
        "red_flags": [],
    }
    if tokens and not vec_info.get("text_tokens"):
        vec_info["text_tokens"] = tokens
    return vec_info


def decide_from_documents(documents: list[Any], *, raw_input: str = "") -> dict[str, Any]:
    """Full decide path: tokenize → LLM deviation filter → vectorize → match → Decider."""
    vec_info = _vectorize_with_token_llm(documents, raw_input=raw_input or "")
    match = match_vector(vec_info["vector"], vec_info["active_features"])
    tokens_summary = {
        "active_features": vec_info["active_features"],
        "text_tokens": vec_info.get("text_tokens") or [],
        "matched_phrases": vec_info.get("matched_phrases") or [],
        "token_filter": vec_info.get("token_filter") or {},
        "features_version": vec_info["features_version"],
    }
    epicrisis = raw_input or "\n\n".join(
        getattr(d, "raw_text", None)
        or (d.get("raw_text") if isinstance(d, dict) else "")
        or ""
        for d in (documents or [])
    )
    result = _decide_llm(match, epicrisis, tokens_summary)
    dj = result.get("decision_json") or {}
    dj["token_filter"] = vec_info.get("token_filter") or {}
    dj["text_tokens"] = vec_info.get("text_tokens") or []
    result["decision_json"] = dj
    return result


def match_only_from_documents(
    documents: list[Any],
    *,
    extra_text: str = "",
    use_llm_filter: bool = True,
) -> dict[str, Any]:
    vec_info = _vectorize_with_token_llm(
        documents,
        raw_input=extra_text or "",
        use_llm_filter=use_llm_filter,
    )
    match = match_vector(vec_info["vector"], vec_info["active_features"])
    return {
        **vec_info,
        "match": match.to_dict(),
    }
