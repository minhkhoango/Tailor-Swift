#!/usr/bin/env python3
# pyright: reportUnusedFunction=false
"""Repo-root pytest config: import path + the metered-API network guard.

Two jobs, both load-bearing for the fast suite:

1. Put the repo root on ``sys.path`` so ``import tailor`` (and ``tailor.core.*``)
   resolves regardless of where pytest is launched from.
2. **Network guard** (PLAN §Tests, tier 1): every test runs with
   ``ANTHROPIC_API_KEY`` scrubbed from the environment and ``anthropic.Anthropic``
   replaced by a tripwire that raises. No test can construct the real client or
   read the key by accident -- the metered API is unreachable from the suite. The
   one e2e smoke that DOES hit the API is run by hand, never collected by pytest.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _no_metered_api(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scrub the key and trip-wire the real client for every collected test."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    try:
        import anthropic
    except ImportError:
        return

    def _tripwire(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError(
            "network guard: a test tried to construct the real Anthropic client. "
            "Inject a fake llm into run()/tailor_one()/why() instead.")

    monkeypatch.setattr(anthropic, "Anthropic", _tripwire)
