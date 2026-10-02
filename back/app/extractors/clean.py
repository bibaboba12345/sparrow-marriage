"""Text cleanup helpers for extracted documents."""

from __future__ import annotations

import re


def clean_text(text: str) -> str:
    if not text:
        return ""
    # normalize newlines / NBSP
    text = text.replace("\u00a0", " ").replace("\r\n", "\n").replace("\r", "\n")
    # collapse spaces inside lines
    text = re.sub(r"[ \t]+", " ", text)
    # trim each line
    lines = [line.strip() for line in text.split("\n")]
    # drop empty runs → max one blank line
    cleaned: list[str] = []
    blank = False
    for line in lines:
        if not line:
            if not blank and cleaned:
                cleaned.append("")
                blank = True
            continue
        cleaned.append(line)
        blank = False
    return "\n".join(cleaned).strip()
