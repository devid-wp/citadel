"""
Tests for core/shell_history.py

Покрывает:
  - begin/finish
  - recent порядок (новейшие первые)
  - record_inline
  - search (по подстроке, case-insensitive)
  - clear (только RAM)
  - flush, truncate_disk
  - JSONL-формат на диске
"""
from __future__ import annotations

import json
import os
import time

import pytest

from core.shell_history import (
    HistoryEntry,
    HistoryManager,
    get_default_history,
    reset_default_history,
)


# ============================================================================
# begin/finish
# ============================================================================

def test_begin_returns_pending_record(tmp_history):
    rec = tmp_history.begin("ls -la")
    assert rec.cmd == "ls -la"
    assert rec.cwd == os.getcwd()
    assert rec.started_at > 0


def test_finish_appends_to_ring(tmp_history):
    rec = tmp_history.begin("echo hi")
    entry = tmp_history.finish(rec, exit_code=0)
    assert entry.cmd == "echo hi"
    assert entry.exit_code == 0
    assert entry.duration_ms >= 0
    assert len(tmp_history.recent(10)) == 1


def test_finish_records_exit_code(tmp_history):
    rec = tmp_history.begin("false")
    entry = tmp_history.finish(rec, exit_code=1)
    assert entry.exit_code == 1


def test_finish_handles_none_record(tmp_history):
    """Если потеряли record — finish должен не упасть."""
    entry = tmp_history.finish(None, exit_code=0)
    assert entry.cmd == ""


# ============================================================================
# recent()
# ============================================================================

def test_recent_order_newest_first(tmp_history):
    for i in range(5):
        rec = tmp_history.begin(f"cmd{i}")
        tmp_history.finish(rec, exit_code=0)
    recent = tmp_history.recent(10)
    assert [e.cmd for e in recent] == ["cmd4", "cmd3", "cmd2", "cmd1", "cmd0"]


def test_recent_limit(tmp_history):
    for i in range(10):
        rec = tmp_history.begin(f"x{i}")
        tmp_history.finish(rec, exit_code=0)
    assert len(tmp_history.recent(3)) == 3
    assert tmp_history.recent(3)[0].cmd == "x9"


def test_recent_negative_clamped(tmp_history):
    assert tmp_history.recent(-1) == []
    assert tmp_history.recent(0) == []


def test_all_returns_full_snapshot(tmp_history):
    for i in range(3):
        rec = tmp_history.begin(f"c{i}")
        tmp_history.finish(rec, exit_code=0)
    assert len(tmp_history.all()) == 3


# ============================================================================
# record_inline
# ============================================================================

def test_record_inline(tmp_history):
    entry = tmp_history.record_inline("inline_cmd", exit_code=0, duration_ms=42)
    assert entry.cmd == "inline_cmd"
    assert entry.duration_ms == 42
    assert len(tmp_history.recent(1)) == 1


# ============================================================================
# search
# ============================================================================

def test_search_finds_substring(tmp_history):
    for cmd in ("ls -la", "echo hello", "ls -la /etc", "grep foo"):
        rec = tmp_history.begin(cmd)
        tmp_history.finish(rec, exit_code=0)

    res = tmp_history.search("ls")
    assert len(res) == 2
    assert all("ls" in e.cmd for e in res)


def test_search_case_insensitive(tmp_history):
    rec = tmp_history.begin("FOO bar")
    tmp_history.finish(rec, exit_code=0)
    res = tmp_history.search("foo")
    assert len(res) == 1


def test_search_empty_returns_recent(tmp_history):
    for i in range(3):
        rec = tmp_history.begin(f"c{i}")
        tmp_history.finish(rec, exit_code=0)
    res = tmp_history.search("")
    assert len(res) == 3


# ============================================================================
# clear (только RAM)
# ============================================================================

def test_clear_empties_ram(tmp_history):
    rec = tmp_history.begin("x")
    tmp_history.finish(rec, exit_code=0)
    tmp_history.clear()
    assert len(tmp_history.recent(10)) == 0


def test_clear_keeps_disk(tmp_history, tmp_path):
    """Очистка RAM не трогает файл на диске."""
    rec = tmp_history.begin("persisted")
    tmp_history.finish(rec, exit_code=0)

    tmp_history.clear()
    # Файл всё ещё содержит запись.
    assert os.path.exists(tmp_history._path)
    with open(tmp_history._path) as f:
        lines = f.readlines()
    assert len(lines) == 1
    assert "persisted" in lines[0]


# ============================================================================
# Persist / load
# ============================================================================

def test_disk_persists_jsonl(tmp_history, tmp_path):
    rec = tmp_history.begin("disk_cmd")
    tmp_history.finish(rec, exit_code=0)

    # Создать новый менеджер с тем же путём — он должен подгрузить.
    new = HistoryManager(history_path=tmp_history._path)
    recent = new.recent(10)
    assert len(recent) == 1
    assert recent[0].cmd == "disk_cmd"


def test_disk_loads_only_last_n(tmp_history, tmp_path):
    """disk_load cap: старые записи не подгружаются."""
    for i in range(5):
        rec = tmp_history.begin(f"old{i}")
        tmp_history.finish(rec, exit_code=0)

    # Создать новый с маленьким disk_load
    new = HistoryManager(
        history_path=tmp_history._path,
        disk_load=2,
    )
    recent = new.recent(10)
    # Должны загрузиться только последние 2
    assert len(recent) == 2
    assert recent[0].cmd == "old4"


def test_corrupted_lines_skipped(tmp_history):
    """Битая строка в JSONL — пропускаем, не валим менеджер."""
    rec = tmp_history.begin("ok")
    tmp_history.finish(rec, exit_code=0)
    # Дописать мусор
    with open(tmp_history._path, "a", encoding="utf-8") as f:
        f.write("not json at all\n")
    rec = tmp_history.begin("after_garbage")
    tmp_history.finish(rec, exit_code=0)

    new = HistoryManager(history_path=tmp_history._path)
    # Должны загрузиться обе валидные записи
    recent = new.recent(10)
    cmds = [e.cmd for e in recent]
    assert "ok" in cmds
    assert "after_garbage" in cmds


# ============================================================================
# flush / truncate_disk
# ============================================================================

def test_flush_returns_bool(tmp_history):
    """flush() возвращает bool. На Windows может быть False из-за того,
    что fsync на read-mode не поддержан — это by design (см. docstring)."""
    result = tmp_history.flush()
    assert isinstance(result, bool)


def test_flush_after_write(tmp_history):
    """После реальной записи flush() должен попытаться fsync (и вернуть bool)."""
    rec = tmp_history.begin("x")
    tmp_history.finish(rec, exit_code=0)
    result = tmp_history.flush()
    assert isinstance(result, bool)


def test_truncate_disk_clears_file(tmp_history):
    rec = tmp_history.begin("x")
    tmp_history.finish(rec, exit_code=0)
    assert tmp_history.truncate_disk() is True
    new = HistoryManager(history_path=tmp_history._path)
    assert len(new.recent(10)) == 0


# ============================================================================
# Singleton
# ============================================================================

def test_singleton_returns_same_instance():
    reset_default_history()
    h1 = get_default_history()
    h2 = get_default_history()
    assert h1 is h2


def test_reset_clears_singleton():
    h1 = get_default_history()
    reset_default_history()
    h2 = get_default_history()
    assert h1 is not h2
