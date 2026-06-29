#!/usr/bin/env python3
# pyright: reportUnusedImport=false
"""Tests for the .env bridge and the missing-key guard.

Two concerns, one file:

  * ``paths.load_env`` -- the small zero-dependency dotenv reader: parsing rules
    (comments, ``export``, quotes, malformed lines), shell-wins precedence, the
    ``override`` escape hatch, and the missing-file no-op.
  * ``llm.LLMClient`` -- that a missing credential raises the clean
    ``MissingAPIKey`` (with an actionable message) *before* the SDK is touched,
    and that a present credential opens the gate (reaching the conftest tripwire,
    proving construction proceeds rather than the gate rejecting it).

``load_env`` writes straight to ``os.environ`` (that is its job), so every test
that exercises it uses a unique throwaway key name and pops it in ``finally`` so
no state leaks between tests.
"""

from __future__ import annotations

import os
from pathlib import Path

import _helpers  # noqa: F401  (path setup)
import pytest

import tailor.llm as llm_mod
from tailor.core.paths import load_env

# A name that is never a real credential and never set by the suite, so writing
# it from a temp .env can't collide with anything the process actually uses.
KEY = "TAILOR_ENV_TEST_KEY"


def _no_env(*_args: object, **_kwargs: object) -> dict[str, str]:
    """A typed stand-in for ``load_env`` that touches nothing -- so a test can
    prove the missing-key guard fires without the real repo ``.env`` leaking in."""
    return {}


def test_parses_value_skipping_comments_and_blanks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(KEY, raising=False)
    env = tmp_path / ".env"
    env.write_text(f"# a comment\n\n{KEY}=sk-ant-123\n", encoding="utf-8")
    try:
        applied = load_env(env)
        assert applied == {KEY: "sk-ant-123"}
        assert os.environ[KEY] == "sk-ant-123"
    finally:
        os.environ.pop(KEY, None)


def test_strips_export_prefix_and_matched_quotes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(KEY, raising=False)
    env = tmp_path / ".env"
    # leading `export `, double-quoted value that itself contains a `#` and spaces
    env.write_text(f'export {KEY}="a value # not-a-comment"\n', encoding="utf-8")
    try:
        applied = load_env(env)
        assert applied[KEY] == "a value # not-a-comment"
    finally:
        os.environ.pop(KEY, None)


def test_malformed_line_is_skipped_not_raised(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(KEY, raising=False)
    env = tmp_path / ".env"
    # a line with no `=` and a line with an empty key are both ignored
    env.write_text(f"garbage-no-equals\n=orphan-value\n{KEY}=ok\n", encoding="utf-8")
    try:
        applied = load_env(env)
        assert applied == {KEY: "ok"}
    finally:
        os.environ.pop(KEY, None)


def test_shell_env_wins_unless_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(KEY, "from-shell")
    env = tmp_path / ".env"
    env.write_text(f"{KEY}=from-file\n", encoding="utf-8")
    # default: an already-set var is left alone, nothing applied
    assert load_env(env) == {}
    assert os.environ[KEY] == "from-shell"
    # override=True: the file value clobbers it (monkeypatch restores on teardown)
    assert load_env(env, override=True) == {KEY: "from-file"}
    assert os.environ[KEY] == "from-file"


def test_missing_file_is_a_noop(tmp_path: Path) -> None:
    assert load_env(tmp_path / "nope.env") == {}


def test_missing_key_raises_clean_actionable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # Stub load_env so the real repo .env (which has a key) can't leak in, then
    # scrub both accepted credential vars: the guard must fire before anthropic.
    monkeypatch.setattr(llm_mod, "load_env", _no_env)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    with pytest.raises(llm_mod.MissingAPIKey) as excinfo:
        llm_mod.LLMClient()
    message = str(excinfo.value)
    assert "ANTHROPIC_API_KEY" in message          # names the var to set
    assert "console.anthropic.com" in message       # tells you where to get one


def test_present_key_opens_gate_and_proceeds(monkeypatch: pytest.MonkeyPatch) -> None:
    # With a credential present the guard must NOT reject; construction proceeds
    # to anthropic.Anthropic(), which conftest trip-wires -- so we expect the
    # tripwire's RuntimeError, NOT MissingAPIKey. That proves the gate opened.
    monkeypatch.setattr(llm_mod, "load_env", _no_env)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-present")
    with pytest.raises(RuntimeError) as excinfo:
        llm_mod.LLMClient()
    assert not isinstance(excinfo.value, llm_mod.MissingAPIKey)
    assert "network guard" in str(excinfo.value)
