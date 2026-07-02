"""
Tests for core/shell_glob.py

Покрывает:
  - is_glob
  - _expand_simple (basic glob, dotfiles, no matches)
  - _expand_doublestar (** recursive)
  - expand_token / expand_tokens
"""
from __future__ import annotations

import os

import pytest

from core.shell_glob import (
    _expand_doublestar,
    _expand_pattern,
    _expand_simple,
    expand_token,
    expand_tokens,
    is_glob,
)
from core.shell_tokenizer import Token, tokenize


# ============================================================================
# is_glob
# ============================================================================

def test_is_glob_star():
    assert is_glob(Token(raw="*.py", value="*.py", kind="word")) is True


def test_is_glob_question():
    assert is_glob(Token(raw="?.txt", value="?.txt", kind="word")) is True


def test_is_glob_bracket():
    assert is_glob(Token(raw="[abc]", value="[abc]", kind="word")) is True


def test_is_glob_no_special():
    assert is_glob(Token(raw="plain", value="plain", kind="word")) is False


def test_is_glob_quoted_no_expand():
    """Заключённый в кавычки glob-паттерн не раскрывается."""
    t = Token(raw="'*.py'", value="*.py", kind="word", has_quotes=True)
    assert is_glob(t) is False


def test_is_glob_wrong_kind():
    t = Token(raw="|", value="|", kind="pipe")
    assert is_glob(t) is False


# ============================================================================
# _expand_simple
# ============================================================================

def test_expand_simple_basic(tmp_path):
    (tmp_path / "a.py").write_text("")
    (tmp_path / "b.py").write_text("")
    (tmp_path / "c.txt").write_text("")

    os.chdir(tmp_path)
    try:
        out = _expand_simple("*.py")
        assert len(out) == 2
        assert all(p.endswith(".py") for p in out)
        assert out == sorted(out)
    finally:
        os.chdir("/")


def test_expand_simple_no_match(tmp_path):
    os.chdir(tmp_path)
    try:
        out = _expand_simple("*.nope")
        # POSIX: ничего не найдено → возвращаем как есть
        assert out == ["*.nope"]
    finally:
        os.chdir("/")


def test_expand_simple_skips_dotfiles(tmp_path):
    (tmp_path / ".hidden").write_text("")
    (tmp_path / "visible").write_text("")

    os.chdir(tmp_path)
    try:
        out = _expand_simple("*")
        assert ".hidden" not in out
        assert "visible" in out
    finally:
        os.chdir("/")


def test_expand_simple_with_dotfiles(tmp_path):
    (tmp_path / ".hidden").write_text("")
    (tmp_path / "visible").write_text("")

    os.chdir(tmp_path)
    try:
        out = _expand_simple("*", dotfiles=True)
        assert ".hidden" in out
        assert "visible" in out
    finally:
        os.chdir("/")


def test_expand_simple_subdir_prefix(tmp_path):
    sub = tmp_path / "d"
    sub.mkdir()
    (sub / "x.py").write_text("")

    os.chdir(tmp_path)
    try:
        out = _expand_simple("d/*.py")
        assert len(out) == 1
        assert out[0].endswith("x.py")
    finally:
        os.chdir("/")


# ============================================================================
# _expand_doublestar
# ============================================================================

def test_expand_doublestar_recursive(tmp_path):
    (tmp_path / "a.py").write_text("")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.py").write_text("")
    deep = sub / "deeper"
    deep.mkdir()
    (deep / "c.py").write_text("")

    os.chdir(tmp_path)
    try:
        out = _expand_doublestar("**/*.py", dotfiles=False)
        basenames = [os.path.basename(p) for p in out]
        assert "a.py" in basenames
        assert "b.py" in basenames
        assert "c.py" in basenames
    finally:
        os.chdir("/")


def test_expand_doublestar_with_prefix(tmp_path):
    sub = tmp_path / "src"
    sub.mkdir()
    (sub / "a.py").write_text("")
    (sub / "b.txt").write_text("")

    os.chdir(tmp_path)
    try:
        out = _expand_doublestar("src/**/*.py", dotfiles=False)
        basenames = [os.path.basename(p) for p in out]
        assert "a.py" in basenames
        assert "b.txt" not in basenames
    finally:
        os.chdir("/")


# ============================================================================
# expand_token / expand_tokens
# ============================================================================

def test_expand_token_non_glob():
    t = Token(raw="foo", value="foo", kind="word")
    out = expand_token(t)
    assert out == [t]


def test_expand_token_glob(tmp_path):
    (tmp_path / "x.py").write_text("")
    (tmp_path / "y.py").write_text("")

    os.chdir(tmp_path)
    try:
        t = Token(raw="*.py", value="*.py", kind="word")
        out = expand_token(t, cwd=str(tmp_path))
        assert len(out) == 2
        assert all(o.kind == "word" for o in out)
        assert all(not o.has_quotes for o in out)
    finally:
        os.chdir("/")


def test_expand_tokens_preserves_non_glob(tmp_path):
    (tmp_path / "x.py").write_text("")
    toks = [
        Token(raw="ls", value="ls", kind="word"),
        Token(raw="*.py", value="*.py", kind="word"),
    ]
    os.chdir(tmp_path)
    try:
        out = expand_tokens(toks)
        # ls + 1 файл = 2 токена
        assert len(out) == 2
        assert out[0].value == "ls"
    finally:
        os.chdir("/")


def test_expand_tokens_keeps_glob_intact_if_no_match(tmp_path):
    toks = [Token(raw="*.nope", value="*.nope", kind="word")]
    os.chdir(tmp_path)
    try:
        out = expand_tokens(toks)
        # Ничего не найдено — оставляем как было
        assert len(out) == 1
        assert out[0].value == "*.nope"
    finally:
        os.chdir("/")
