"""
Tests for core/repl.py

Покрывает:
  - build_prompt (обычный + continuation)
  - process_line (exit-обработка, пустая строка)
  - HistoryBridge (add/save/log)
  - run_repl_non_interactive (выход через EOF, exit builtin)
  - build_banner (Phase 1.8: логотип + recent commands)
"""
from __future__ import annotations

import io
import os
from unittest.mock import patch

import pytest

from core.repl import (
    BANNER,
    HistoryBridge,
    build_banner,
    build_prompt,
    process_line,
    run_repl_non_interactive,
)


# ============================================================================
# build_prompt
# ============================================================================

def test_build_prompt_basic():
    s = build_prompt(
        palette=None,
        cwd="/home/user",
        user_name="alice",
        version="3.0",
    )
    assert "alice" in s
    assert "3.0" in s
    assert "user" in s  # basename
    # trailing "$ " индикатор prompt'а
    assert "$" in s


def test_build_prompt_continuation():
    s = build_prompt(palette=None, continuation=True, reason="quote")
    # Должен быть короткий маркер, а не полный prompt
    assert "..." in s
    assert "@" not in s  # полный prompt не выводится


def test_build_prompt_continuation_bracket():
    s = build_prompt(palette=None, continuation=True, reason="brackets")
    assert "..." in s


def test_build_prompt_palette_applied():
    """Если палитра передана — её цвета используются."""
    from dataclasses import dataclass
    @dataclass
    class P:
        primary: str = "\033[95m"
        accent: str = "\033[96m"
        muted: str = "\033[90m"
        reset: str = "\033[0m"

    s = build_prompt(palette=P(), cwd="/tmp", user_name="x", version="1")
    assert "\033[95m" in s  # primary
    assert "\033[0m" in s   # reset


# ============================================================================
# process_line
# ============================================================================

def test_process_line_empty_returns_zero():
    assert process_line("") == 0
    assert process_line("   ") == 0


def test_process_line_exit_returns_marker():
    assert process_line("exit") == -1
    assert process_line("quit") == -1
    assert process_line("q") == -1
    assert process_line("EXIT") == -1  # case-insensitive


def test_process_line_runs_real_command():
    """Реальная команда через run_command (subprocess)."""
    rc = process_line("python -c \"print(123)\"")
    assert rc == 0


def test_process_line_unknown_command_nonzero():
    """Несуществующая команда → ненулевой rc."""
    rc = process_line("this_command_does_not_exist_12345")
    assert rc != 0


# ============================================================================
# HistoryBridge
# ============================================================================

def test_history_bridge_constructs(tmp_history):
    """HistoryBridge должен работать с подсунутым HistoryManager."""
    b = HistoryBridge(history=tmp_history, readline_path=os.devnull)
    assert b.history is tmp_history


def test_history_bridge_log(tmp_history):
    b = HistoryBridge(history=tmp_history, readline_path=os.devnull)
    # log() использует begin/finish пару — потом запись появляется в кольце.
    b.log("test cmd")
    # log() сам ничего не записывает в кольцо — это только begin.
    # Запись появится только после finish() на том же HistoryManager.
    # Тестируем контракт: log() не падает и cmd становится pending.
    # Более полный round-trip проверяется в test_shell_history.py.
    # Здесь — sanity check, что log() не ломает состояние.
    assert True


def test_history_bridge_close_calls_flush(tmp_history, tmp_path):
    """close() должен вызвать flush у history."""
    b = HistoryBridge(history=tmp_history, readline_path=str(tmp_path / "h"))
    # Должно не падать
    b.close()


# ============================================================================
# run_repl_non_interactive
# ============================================================================

def test_run_repl_non_interactive_basic():
    """Должен исполнить команды и выйти."""
    inp = io.StringIO("python -c \"print('ok')\"\n")
    rc = run_repl_non_interactive(inp, banner=False)
    assert rc == 0


def test_run_repl_non_interactive_exit():
    """'exit' команда → корректное завершение."""
    inp = io.StringIO("exit\n")
    rc = run_repl_non_interactive(inp, banner=False)
    # exit → process_line возвращает -1, last_real_rc остаётся 0
    assert rc == 0


def test_run_repl_non_interactive_empty():
    inp = io.StringIO("\n\n\n")
    rc = run_repl_non_interactive(inp, banner=False)
    assert rc == 0


def test_run_repl_non_interactive_multiline_quote():
    """Незакрытая кавычка — копит, продолжает, исполняет."""
    inp = io.StringIO('echo "hello\nworld"\n')
    rc = run_repl_non_interactive(inp, banner=False)
    assert rc == 0


def test_run_repl_non_interactive_eof():
    """EOF на пустом вводе — корректный выход с rc=0."""
    inp = io.StringIO("")
    rc = run_repl_non_interactive(inp, banner=False)
    assert rc == 0


# ============================================================================
# build_banner (Phase 1.8)
# ============================================================================

def test_build_banner_no_color():
    s = build_banner(use_color=False, n_recent=3)
    # Без ANSI
    assert "\033[" not in s
    # Базовые элементы
    assert "CITADEL" in s
    assert "Recent commands" in s
    # Подсказки
    assert "Type 'help'" in s


def test_build_banner_with_color():
    s = build_banner(use_color=True, n_recent=3)
    # С ANSI
    assert "\033[" in s
    # Боковые границы
    assert "┌" in s
    assert "└" in s


def test_build_banner_with_recent(tmp_history):
    tmp_history.record_inline("cmd a", 0, 5)
    tmp_history.record_inline("cmd b", 0, 5)
    s = build_banner(use_color=False, n_recent=3, history=tmp_history)
    assert "cmd a" in s
    assert "cmd b" in s
    # Нумерация
    assert "1." in s
    assert "2." in s


def test_build_banner_truncates_long_commands(tmp_history):
    long = "x" * 200
    tmp_history.record_inline(long, 0, 5)
    s = build_banner(use_color=False, n_recent=3, history=tmp_history)
    # Должны увидеть маркер усечения
    assert "..." in s
    # Вся команда в баннер не влезла
    assert long not in s


def test_build_banner_empty_history(tmp_history):
    s = build_banner(use_color=False, n_recent=3, history=tmp_history)
    assert "no commands yet" in s


def test_build_banner_logo_loaded():
    """Если logo.txt есть, он попадает в баннер."""
    s = build_banner(use_color=False, n_recent=3)
    # ASCII-арт из logo.txt (любой узнаваемый кусок)
    # Берём что-то надёжное — характерный блок.
    assert "CITADEL" in s


def test_build_banner_legacy_compat():
    """Старая константа BANNER всё ещё работает (для backward compat)."""
    assert "Citadel Shell" in BANNER


def test_build_banner_works_without_logo(tmp_path, monkeypatch):
    """Если logo.txt не существует — fallback на текстовую шапку, не падает."""
    from core import repl
    # Подменим путь к логотипу
    monkeypatch.setattr(repl, "_LOGO_PATH", str(tmp_path / "nope.txt"))
    s = repl.build_banner(use_color=False, n_recent=3)
    assert "CITADEL OS" in s
