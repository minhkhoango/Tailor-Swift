#!/usr/bin/env python3
# pyright: reportUnusedFunction=false
"""Repo-root pytest config: import path, the metered-API network guard, and --io.

Three jobs:

1. Put the repo root on ``sys.path`` so ``import tailor`` (and ``tailor.core.*``)
   resolves regardless of where pytest is launched from.
2. **Network guard** (PLAN §Tests, tier 1): every test runs with
   ``ANTHROPIC_API_KEY`` scrubbed from the environment and ``anthropic.Anthropic``
   replaced by a tripwire that raises. No test can construct the real client or
   read the key by accident -- the metered API is unreachable from the suite. The
   ONE exception is a test marked ``@pytest.mark.live``: it is allowed to build the
   real client (it self-skips when no key is set), so the e2e smoke can be hand-run.
3. **``--io``**: an opt-in flag that dumps each e2e/fixture subject's full I/O
   (prompt SENT, slots RECEIVED, tool FIT/HONESTY output, SHIPPED path) to the
   terminal, untruncated -- so you can read exactly what the model and tools did
   the way the user experiences it. Use the ``io_report`` fixture to emit blocks.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable, Protocol, cast

import pytest
from _pytest.nodes import Node


class _CaptureManager(Protocol):
    """The slice of pytest's capturemanager plugin we touch -- typed so strict
    pyright is happy without leaning on the plugin's untyped ``_PluggyPlugin``."""

    def global_and_fixture_disabled(self) -> Any: ...

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--io", action="store_true", default=False,
        help="dump each subject's LLM + tool I/O (prompt/response/fit/honesty) to the terminal")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "live: real-Anthropic smoke; needs ANTHROPIC_API_KEY + pdflatex (hand-run, self-skips)")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Deselect the metered ``@pytest.mark.live`` smoke unless the user explicitly
    opts in with ``-m live``. This composes with any other ``-m`` filter (e.g. the
    documented ``-m "not inspect"`` fast run) -- unlike ``addopts = -m "not live"``,
    which pytest's single-valued ``-m`` would clobber. ``-m live`` runs them;
    ``-m "not live"`` is handled by pytest's own deselection."""
    markexpr = cast(str, getattr(config.option, "markexpr", "") or "")
    if "live" in markexpr:
        return
    skip_live = pytest.mark.skip(reason="live API test; run with -m live")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


@pytest.fixture(autouse=True)
def _no_metered_api(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Scrub the key and trip-wire the real client for every collected test -- except
    a ``@pytest.mark.live`` test, which is allowed to reach the real API on purpose."""
    node = cast(Node, getattr(request, "node"))
    if node.get_closest_marker("live") is not None:
        return
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


@pytest.fixture
def io_report(request: pytest.FixtureRequest) -> Callable[..., None]:
    """Return a ``report(subject, **sections)`` callable that, only under ``--io``,
    prints labeled untruncated I/O blocks straight to the terminal.

    Capture is disabled around the print so the blocks show without needing ``-s``.
    Section kwargs render in call order, e.g.
    ``io_report(name, SENT=jd, RECEIVED=slots, FIT=text, HONESTY=flags, SHIPPED=path)``.
    """
    enabled = bool(request.config.getoption("--io"))
    capman = cast("_CaptureManager | None",
                  request.config.pluginmanager.getplugin("capturemanager"))

    def report(subject: str, **sections: object) -> None:
        if not enabled:
            return
        bar = "=" * 78
        lines = [f"\n{bar}", f"  IO  {subject}", bar]
        for label, body in sections.items():
            lines.append(f"----- {label} " + "-" * max(0, 71 - len(label)))
            lines.append("(empty)" if body in (None, "") else str(body))
        text = "\n".join(lines) + "\n"
        if capman is not None:
            with capman.global_and_fixture_disabled():
                print(text)
        else:
            print(text)

    return report
