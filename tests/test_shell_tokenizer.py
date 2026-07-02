"""
Tests for core/shell_tokenizer.py

Покрывает:
  - tokenize: операторы, кавычки, escape, переменные, комментарии
  - line_continues / continuation_reason
  - bracket_balance
"""
from __future__ import annotations

import pytest

from core.shell_tokenizer import (
    Token,
    TokenizeResult,
    bracket_balance,
    continuation_reason,
    is_control,
    is_redirection,
    line_continues,
    tokenize,
)


# ============================================================================
# Базовый парсинг
# ============================================================================

def test_empty_string():
    res = tokenize("")
    assert res.tokens == []
    assert res.ok


def test_simple_words():
    res = tokenize("ls -la /tmp")
    assert res.ok
    assert len(res.tokens) == 3
    assert [t.value for t in res.tokens] == ["ls", "-la", "/tmp"]
    assert all(t.kind == "word" for t in res.tokens)


def test_single_command():
    res = tokenize("echo")
    assert res.ok
    assert len(res.tokens) == 1
    assert res.tokens[0].value == "echo"


# ============================================================================
# Операторы
# ============================================================================

def test_pipe_operator():
    res = tokenize("ls | grep foo")
    assert res.ok
    kinds = [t.kind for t in res.tokens]
    assert "pipe" in kinds
    assert kinds.count("pipe") == 1


def test_double_amp_and():
    """&& не должен разваливаться на два &."""
    res = tokenize("cmd1 && cmd2")
    assert res.ok
    kinds = [t.kind for t in res.tokens]
    assert kinds.count("and") == 1
    assert "&" not in [t.value for t in res.tokens]


def test_double_pipe_or():
    res = tokenize("cmd1 || cmd2")
    assert res.ok
    kinds = [t.kind for t in res.tokens]
    assert kinds.count("or") == 1


def test_redirect_out():
    res = tokenize("echo hi > file.txt")
    assert res.ok
    assert any(t.kind == "redir_out" for t in res.tokens)


def test_redirect_append():
    res = tokenize("echo hi >> file.txt")
    assert res.ok
    assert any(t.kind == "redir_app" for t in res.tokens)


def test_redirect_in():
    res = tokenize("sort < input.txt")
    assert res.ok
    assert any(t.kind == "redir_in" for t in res.tokens)


def test_redirect_stderr():
    res = tokenize("cmd 2> err.log")
    assert res.ok
    assert any(t.kind == "redir_err" for t in res.tokens)


def test_redirect_merge_2and1():
    res = tokenize("cmd 2>&1")
    assert res.ok
    assert any(t.kind == "redir_merge" for t in res.tokens)


def test_redirect_merge_not_split():
    """2>&1 не должен распадаться на 2> и &1."""
    res = tokenize("cmd 2>&1")
    redir = [t for t in res.tokens if t.kind in ("redir_err", "redir_merge", "background")]
    assert len(redir) == 1
    assert redir[0].kind == "redir_merge"


def test_pipe_err():
    res = tokenize("cmd |& other")
    assert res.ok
    assert any(t.kind == "pipe_err" for t in res.tokens)


def test_pipe_err_not_split():
    res = tokenize("cmd |& other")
    assert res.ok
    assert sum(1 for t in res.tokens if t.kind in ("pipe", "pipe_err")) == 1


def test_semicolon():
    res = tokenize("cmd1 ; cmd2")
    assert res.ok
    assert any(t.kind == "semicolon" for t in res.tokens)


def test_background():
    res = tokenize("sleep 10 &")
    assert res.ok
    assert any(t.kind == "background" for t in res.tokens)


# ============================================================================
# Кавычки
# ============================================================================

def test_single_quotes_literal():
    """В '...' ничего не раскрывается, но $ как символ сохраняется."""
    res = tokenize("echo '$HOME'")
    assert res.ok
    word = res.tokens[-1]
    assert word.value == "$HOME"
    assert word.has_quotes is True


def test_double_quotes_keep_dollar():
    """В "..." $VAR сохраняется для VariableStore."""
    res = tokenize('echo "hello $USER"')
    assert res.ok
    word = res.tokens[-1]
    assert "$USER" in word.value
    assert word.has_quotes is True


def test_nested_quotes():
    res = tokenize("echo \"it's me\"")
    assert res.ok
    assert res.tokens[-1].has_quotes is True


def test_unterminated_single_quote():
    res = tokenize("echo 'hello")
    assert not res.ok
    assert any("Unterminated" in e.message for e in res.errors)


def test_unterminated_double_quote():
    res = tokenize('echo "hello')
    assert not res.ok
    assert any("Unterminated" in e.message for e in res.errors)


# ============================================================================
# Escape
# ============================================================================

def test_escape_dollar():
    res = tokenize(r"echo \$HOME")
    assert res.ok
    assert res.tokens[-1].value == "$HOME"


def test_escape_pipe():
    res = tokenize(r"echo a\|b")
    assert res.ok
    # Должно быть одно слово a|b, не pipe-оператор
    assert not any(t.kind == "pipe" for t in res.tokens)
    assert res.tokens[-1].value == "a|b"


def test_windows_path_kept_literal():
    """C:\\Users — двойной бэкслэш НЕ escape-последовательность."""
    res = tokenize(r"C:\Users\file.txt")
    assert res.ok
    assert res.tokens[0].value == r"C:\Users\file.txt"


# ============================================================================
# Комментарии
# ============================================================================

def test_comment_strips_rest():
    res = tokenize("ls -la # show all")
    assert res.ok
    assert "show" not in " ".join(t.value for t in res.tokens)


def test_comment_inside_quotes_kept():
    """# внутри "..." — литерал, не комментарий."""
    res = tokenize('echo "this is # not a comment"')
    assert res.ok
    assert any("#" in t.value for t in res.tokens)


# ============================================================================
# line_continues
# ============================================================================

def test_line_continues_backslash():
    assert line_continues("echo hello \\") is True


def test_line_continues_double_backslash_no():
    """Заканчивается на \\ — это литеральный бэкслэш, не продолжение."""
    assert line_continues("echo a\\b") is False


def test_line_continues_unterminated_quote():
    assert line_continues('echo "hello') is True


def test_line_continues_open_bracket():
    assert line_continues("echo (") is True
    assert line_continues("if [ x ]; then") is False  # balanced
    assert line_continues("if [ x; then") is True


def test_line_continues_normal():
    assert line_continues("ls -la") is False
    assert line_continues("") is False


# ============================================================================
# continuation_reason
# ============================================================================

def test_continuation_reason_quote():
    assert continuation_reason('echo "hi') == "quote"


def test_continuation_reason_bracket():
    assert continuation_reason("if ( x )") == ""  # balanced
    assert continuation_reason("if ( x") == "brackets"


def test_continuation_reason_backslash():
    assert continuation_reason("echo a \\") == "backslash"


# ============================================================================
# bracket_balance
# ============================================================================

def test_bracket_balance_balanced():
    toks = tokenize("echo (a + b)").tokens
    assert bracket_balance(toks) == 0


def test_bracket_balance_unbalanced_open():
    toks = tokenize("echo (a + b").tokens
    assert bracket_balance(toks) == 1


def test_bracket_balance_inside_quotes_ignored():
    """Скобки внутри "..." не считаются."""
    toks = tokenize('echo "(hello)"').tokens
    assert bracket_balance(toks) == 0


def test_bracket_balance_doesnt_go_negative():
    """Закрывающая без открывающей — depth остаётся 0, не уходит в минус."""
    toks = tokenize("echo )(").tokens
    depth = bracket_balance(toks)
    assert depth >= 0


# ============================================================================
# Helpers
# ============================================================================

def test_is_redirection():
    toks = tokenize("a > b").tokens
    assert is_redirection(toks[1].kind) is True
    assert is_redirection(toks[0].kind) is False


def test_is_control():
    toks = tokenize("a | b").tokens
    assert is_control(toks[1].kind) is True
    assert is_control(toks[0].kind) is False
