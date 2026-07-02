"""
Tests for core/shell_state.py

Покрывает:
  - CRUD: get/set/unset
  - Подстановка: $VAR, ${VAR}, неизвестные
  - Экспорт в os.environ
  - refresh_pwd
  - Валидация имён
  - expand_tokens
"""
from __future__ import annotations

import os

import pytest

from core.shell_state import VariableStore, _is_valid_name


# ============================================================================
# set / get / unset
# ============================================================================

def test_set_and_get(fresh_store):
    fresh_store.set("FOO", "bar")
    assert fresh_store.get("FOO") == "bar"


def test_set_default_for_missing(fresh_store):
    assert fresh_store.get("MISSING", "fallback") == "fallback"
    assert fresh_store.get("MISSING") == ""


def test_unset(fresh_store):
    fresh_store.set("FOO", "bar")
    assert fresh_store.unset("FOO") is True
    assert fresh_store.get("FOO") == ""


def test_unset_missing(fresh_store):
    assert fresh_store.unset("NEVER_SET") is False


def test_get_reads_from_environ(fresh_store):
    os.environ["FROM_ENV"] = "envvalue"
    try:
        assert fresh_store.get("FROM_ENV") == "envvalue"
    finally:
        del os.environ["FROM_ENV"]


# ============================================================================
# expand
# ============================================================================

def test_expand_simple_var(fresh_store):
    fresh_store.set("NAME", "citadel")
    assert fresh_store.expand("hello $NAME") == "hello citadel"


def test_expand_braced_var(fresh_store):
    fresh_store.set("X", "42")
    assert fresh_store.expand("value=${X}_end") == "value=42_end"


def test_expand_unknown_var_is_empty(fresh_store):
    assert fresh_store.expand("[$NOPE]") == "[]"


def test_expand_no_dollars(fresh_store):
    assert fresh_store.expand("plain text") == "plain text"


def test_expand_empty_string(fresh_store):
    assert fresh_store.expand("") == ""


def test_expand_mixed(fresh_store):
    fresh_store.set("A", "1")
    fresh_store.set("B", "2")
    out = fresh_store.expand("$A-${B}-$C")
    assert out == "1-2-"


def test_expand_in_dquote_style():
    """Token с has_quotes=True всё равно expand'ится — это работа VariableStore,
    а не токенизатора. Внутри '...' (squote) — на уровне Token мы не трогаем.
    Здесь expand() работает по строке, без оглядки на кавычки."""
    s = VariableStore()
    s.set("U", "alice")
    assert s.expand('"$U"') == '"alice"'


# ============================================================================
# Экспорт
# ============================================================================

def test_export_to_environ(fresh_store):
    fresh_store.set("EXPORTED", "yes", export=True)
    assert os.environ.get("EXPORTED") == "yes"
    del os.environ["EXPORTED"]


def test_unset_removes_from_environ(fresh_store):
    fresh_store.set("TEMP_X", "v", export=True)
    assert os.environ.get("TEMP_X") == "v"
    fresh_store.unset("TEMP_X")
    assert "TEMP_X" not in os.environ


def test_set_without_export_doesnt_touch_environ(fresh_store):
    if "LOCAL_VAR" in os.environ:
        del os.environ["LOCAL_VAR"]
    fresh_store.set("LOCAL_VAR", "x")
    assert "LOCAL_VAR" not in os.environ


def test_as_env(fresh_store):
    fresh_store.set("MIXED", "1")
    env = fresh_store.as_env()
    assert "MIXED" in env
    assert env["MIXED"] == "1"


def test_as_env_with_extra(fresh_store):
    env = fresh_store.as_env({"FOO": "bar"})
    assert env["FOO"] == "bar"


# ============================================================================
# Builtins
# ============================================================================

def test_builtin_pwd(fresh_store):
    assert fresh_store.get("PWD") == os.getcwd()


def test_builtin_user(fresh_store):
    assert fresh_store.get("USER") != ""


def test_refresh_pwd(fresh_store, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fresh_store.refresh_pwd(str(tmp_path))
    assert fresh_store.get("PWD") == str(tmp_path)


# ============================================================================
# Validation
# ============================================================================

def test_invalid_name_raises(fresh_store):
    with pytest.raises(ValueError):
        fresh_store.set("1BAD", "x")
    with pytest.raises(ValueError):
        fresh_store.set("WITH-DASH", "x")
    with pytest.raises(ValueError):
        fresh_store.set("WITH SPACE", "x")


def test_is_valid_name():
    assert _is_valid_name("FOO") is True
    assert _is_valid_name("_x") is True
    assert _is_valid_name("A1") is True
    assert _is_valid_name("") is False
    assert _is_valid_name("1A") is False
    assert _is_valid_name("A-B") is False


# ============================================================================
# all()
# ============================================================================

def test_all_merges_environ_and_store(fresh_store):
    os.environ["OUTSIDE"] = "ext"
    try:
        fresh_store.set("INSIDE", "int")
        snap = fresh_store.all()
        assert snap["OUTSIDE"] == "ext"
        assert snap["INSIDE"] == "int"
    finally:
        del os.environ["OUTSIDE"]


# ============================================================================
# expand_tokens
# ============================================================================

def test_expand_tokens_only_words():
    s = VariableStore()
    s.set("V", "42")
    from core.shell_tokenizer import Token, tokenize
    toks = tokenize("echo $V > out").tokens

    expanded = s.expand_tokens(toks)
    # word'ы подменены, redir — нет
    assert expanded[0].value == "echo"
    assert expanded[1].value == "42"
    assert expanded[2].kind == "redir_out"
    assert expanded[3].value == "out"
