"""Load back/.env so Cloud.ru / LLM keys are available for tokenize tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from dotenv import load_dotenv

_BACK_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_BACK_ROOT / ".env", override=False)


@pytest.fixture(scope="session")
def protocols_root() -> Path:
    return _BACK_ROOT.parent / "СМ-Клиника-протоколы" / "протоколы"
