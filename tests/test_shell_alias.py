"""
Tests for core/shell_alias.py

Покрывает:
  - normalize_alias: 3 формата (str, dict, AliasEntry)
  - expand_alias_tokens: variadic ($@), positional ($N), trailing args
  - recursion guard (цепочки алиасов)
  - add_alias / remove_alias
"""
from __future__ import annotations

import os

import pytest

from core.shell_alias import (
    AliasEntry,
    add_alias,
    expand_alias_tokens,
    normalize_alias,
    remove_alias,
)


# ============================================================================
# normalize_alias
# ============================================================================

def test_normalize_alias_string():
    e = normalize_alias("ll", "ls -la")
    assert isinstance(e, AliasEntry)
    assert e.name == "ll"
    assert e.body == "ls -la"
    assert e.arg_count == -1


def test_normalize_alias_aliasentry_passthrough():
    original = AliasEntry(name="g", body="git $@", arg_count=-1)
    e = normalize_alias("g", original)
    assert e is original


def test_normalize_alias_dict():
    e = normalize_alias("g", {"body": "git $1 $@", "args": 2})
    assert e.body == "git $1 $@"
    assert e.arg_count == 2


def test_normalize_alias_json_string():
    """Legacy JSON-encoded entries на диске."""
    import json
    raw = json.dumps({"body": "echo $@", "args": -1})
    e = normalize_alias("e", raw)
    assert e.body == "echo $@"
    assert e.arg_count == -1


def test_normalize_alias_broken_json_falls_back():
    """Битый JSON в строке — fallback на plain string body."""
    e = normalize_alias("x", "{not valid json}")
    assert e.body == "{not valid json}"


def test_normalize_alias_unsupported_type_raises():
    with pytest.raises(ValueError):
        normalize_alias("x", 42)  # type: ignore[arg-type]


# ============================================================================
# expand_alias_tokens
# ============================================================================

def test_expand_simple_alias():
    m = {"ll": AliasEntry("ll", "ls -la", -1)}
    out = expand_alias_tokens(["ll"], m)
    assert out == ["ls", "-la"]


def test_expand_variadic_with_args():
    m = {"ll": AliasEntry("ll", "ls -la $@", -1)}
    out = expand_alias_tokens(["ll", "/etc", "/var"], m)
    assert out == ["ls", "-la", "/etc", "/var"]


def test_expand_positional_args():
    """$1 берёт первый user_arg, $@ — все user_args (POSIX-overlap).
    Тело: 'git $1 $@' + args=['commit', '-m', 'msg'] →
          'git commit commit -m msg' ($@ дублирует первый аргумент — by design)."""
    m = {"g": AliasEntry("g", "git $1 $@", -1)}
    out = expand_alias_tokens(["g", "commit", "-m", "msg"], m)
    assert out == ["git", "commit", "commit", "-m", "msg"]


def test_expand_positional_only():
    """$1 без $@ — корректный trailing."""
    m = {"g": AliasEntry("g", "git $1", -1)}
    out = expand_alias_tokens(["g", "commit"], m)
    assert out == ["git", "commit"]


def test_expand_positional_first_with_at():
    """$1 + $@: $@ = все user_args (текущая семантика, не POSIX-strict)."""
    m = {"x": AliasEntry("x", "echo $1 $@", -1)}
    out = expand_alias_tokens(["x", "a", "b"], m)
    # $1 -> "a", $@ -> ["a", "b"]
    assert out == ["echo", "a", "a", "b"]


def test_expand_positional_out_of_range():
    """$5 при 2 user_args — пусто. Trailing отключён (использован позиционный)."""
    m = {"x": AliasEntry("x", "echo $5", -1)}
    out = expand_alias_tokens(["x", "a", "b"], m)
    # $5 out of range → не подставляется, has_pos_ref=True → trailing подавлен
    assert out == ["echo"]


def test_expand_trailing_args_when_no_at():
    """Без $@ в body — user_args дописываются в конец (POSIX)."""
    m = {"g": AliasEntry("g", "git", -1)}
    out = expand_alias_tokens(["g", "status"], m)
    assert out == ["git", "status"]


def test_expand_no_alias_match():
    m = {"ll": AliasEntry("ll", "ls -la", -1)}
    assert expand_alias_tokens(["unknown", "arg"], m) == ["unknown", "arg"]


def test_expand_empty_argv():
    assert expand_alias_tokens([]) == []


def test_expand_recursion_chain():
    """alias.g → alias.git, alias.git → git."""
    m = {
        "g": AliasEntry("g", "git", -1),
        "git": AliasEntry("git", "gitcmd", -1),
    }
    out = expand_alias_tokens(["g", "status"], m)
    assert out == ["gitcmd", "status"]


def test_expand_recursion_guard():
    """Циклическая цепочка не должна уйти в бесконечность."""
    m = {
        "a": AliasEntry("a", "b", -1),
        "b": AliasEntry("b", "a", -1),
    }
    # Не падаем, depth ограничен.
    out = expand_alias_tokens(["a"], m)
    assert isinstance(out, list)


# ============================================================================
# add/remove alias
# ============================================================================

def test_add_alias_simple_legacy(isolated_config):
    """Без $@ и $N — сохраняем как plain string."""
    add_alias("foo", "echo bar")
    from system.user_config import get_aliases
    aliases = get_aliases()
    assert aliases.get("foo") == "echo bar"


def test_add_alias_with_at(isolated_config):
    """С $@ — JSON-обёртка для parse в normalize_alias."""
    add_alias("ll", "ls -la $@")
    from system.user_config import get_aliases
    raw = get_aliases().get("ll")
    assert isinstance(raw, str)
    assert raw.startswith("{")
    # Нормализуем и проверяем
    e = normalize_alias("ll", raw)
    assert "$@" in e.body


def test_remove_alias(isolated_config):
    add_alias("temp", "echo x")
    assert remove_alias("temp") is True
    assert remove_alias("temp") is False  # уже нет


def test_add_alias_persists_via_user_config(isolated_config):
    """Проверяем что add_alias пишет в user_config.json (round-trip)."""
    from system.user_config import get_aliases
    add_alias("xyz", "echo xyz")
    aliases = get_aliases()
    assert "xyz" in aliases
    # Тело или plain string, или JSON-обёртка
    raw = aliases["xyz"]
    assert "echo xyz" in raw


def test_add_then_remove_alias(isolated_config):
    """Полный round-trip: добавили, удалили, проверка."""
    from system.user_config import get_aliases
    add_alias("ephemeral", "echo x")
    assert "ephemeral" in get_aliases()
    assert remove_alias("ephemeral") is True
    assert "ephemeral" not in get_aliases()
    # Повторный remove → False
    assert remove_alias("ephemeral") is False
