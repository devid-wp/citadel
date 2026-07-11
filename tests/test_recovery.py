"""
Tests for system/recovery.py — Phase 2.5 (session snapshot).

Покрывает:
  1. snapshot_session пишет корректный JSON в ~/.citadel_recovery/.
  2. recent_cmds через provider вытаскиваются лениво.
  3. crash-режим принимает traceback.
  4. install_recovery_hooks() подменяет sys.excepthook и пишет снапшот
     при непойманном исключении.
  5. set_session_state() обновляет cwd/истории.
  6. _prune_old_snapshots оставляет только N свежих файлов.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest


@pytest.fixture
def isolated_recovery_dir(monkeypatch, tmp_path):
    """
    Подменяет RECOVERY_DIR в system.recovery на tmp_path.
    Снести реальный ~/.citadel_recovery в тесте нельзя — он может содержать
    данные прошлых сессий.
    """
    import system.recovery as r
    monkeypatch.setattr(r, "RECOVERY_DIR", str(tmp_path))
    monkeypatch.setattr(r, "RECOVERY_KEEP", 3)
    # Пересоздаём ensure/prune с новым путём через monkeypatch на module-level
    # функции — они замыкают RECOVERY_DIR по module globals, так что setattr
    # достаточно.
    return tmp_path


# ============================================================================
# 1. snapshot_session пишет JSON
# ============================================================================

def test_snapshot_session_writes_json(isolated_recovery_dir):
    import system.recovery as r
    p = r.snapshot_session(
        reason=r.REASON_EXIT,
        cwd="D:/citadel",
        recent_cmds=["ls", "ps"],
    )
    assert p is not None
    assert os.path.isfile(p)
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["schema"] == "citadel.recovery/v1"
    assert data["reason"] == "exit"
    assert data["cwd"] == "D:/citadel"
    assert data["recent_cmds"] == ["ls", "ps"]
    assert "ts" in data and "ts_human" in data


# ============================================================================
# 2. provider-вариант
# ============================================================================

def test_snapshot_session_uses_provider(isolated_recovery_dir):
    import system.recovery as r
    provider_called = {"n": 0}

    def prov():
        provider_called["n"] += 1
        return ["alpha", "beta"]

    p = r.snapshot_session(reason=r.REASON_INTERRUPT, recent_cmds_provider=prov)
    assert provider_called["n"] == 1
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["recent_cmds"] == ["alpha", "beta"]


def test_snapshot_session_provider_failure_returns_default(isolated_recovery_dir):
    import system.recovery as r

    def bad_prov():
        raise OSError("disk full")

    p = r.snapshot_session(reason=r.REASON_CRASH, recent_cmds_provider=bad_prov)
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Дефолт — пустой список, не падаем.
    assert data["recent_cmds"] == []


# ============================================================================
# 3. crash-режим с traceback
# ============================================================================

def test_snapshot_crash_includes_traceback(isolated_recovery_dir):
    import system.recovery as r
    tb = "Traceback (most recent call last):\n  File x\n    raise X\nX: boom\n"
    p = r.snapshot_session(
        reason=r.REASON_CRASH,
        cwd="D:/citadel",
        recent_cmds=["kill 9999"],
        traceback_text=tb,
    )
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["traceback"] == tb


def test_snapshot_session_extracts_traceback_from_exc(isolated_recovery_dir):
    import system.recovery as r
    try:
        raise ValueError("from exc")
    except ValueError:
        p = r.snapshot_session(reason=r.REASON_CRASH, cwd=".", exc=sys.exc_info()[1])
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "ValueError: from exc" in data["traceback"]


# ============================================================================
# 4. install_recovery_hooks + excepthook
# ============================================================================

def test_install_recovery_hooks_replaces_excepthook(isolated_recovery_dir):
    import system.recovery as r
    original = sys.excepthook
    try:
        set_state = r.install_recovery_hooks(initial_cwd="D:/x", recent_cmds=[])
        assert sys.excepthook is not original
        # Триггерим excepthook напрямую (как это делает Python при крахе).
        try:
            raise RuntimeError("boom-from-test")
        except RuntimeError:
            typ, val, tb = sys.exc_info()
            sys.excepthook(typ, val, tb)
        # Должен появиться снапшот.
        snaps = r.list_recovery_snapshots()
        assert len(snaps) == 1
        assert snaps[0]["reason"] == "crash"
        assert "RuntimeError: boom-from-test" in snaps[0].get("traceback", "")
    finally:
        sys.excepthook = original


# ============================================================================
# 5. set_session_state обновляет cwd/history
# ============================================================================

def test_set_session_state_updates_cwd_and_history(isolated_recovery_dir):
    import system.recovery as r
    set_state = r.install_recovery_hooks(initial_cwd="D:/start", recent_cmds=["a"])

    set_state(cwd="D:/middle", recent_cmds=["a", "b", "c"])
    set_state(cwd="D:/end", recent_cmds=["a", "b", "c", "d", "e"])

    # Триггерим снапшот через excepthook.
    try:
        raise RuntimeError("state-test")
    except RuntimeError:
        typ, val, tb = sys.exc_info()
        sys.excepthook(typ, val, tb)

    snaps = r.list_recovery_snapshots()
    assert len(snaps) == 1
    # Последний set_session_state выиграл.
    assert snaps[0]["cwd"] == "D:/end"
    # recent_cmds обрезаны до 20 (тут всего 5, но capping работает).
    assert snaps[0]["recent_cmds"] == ["a", "b", "c", "d", "e"]


# ============================================================================
# 6. _prune_old_snapshots оставляет только N свежих
# ============================================================================
def test_prune_keeps_only_n_snapshots(isolated_recovery_dir):
    import time
    import system.recovery as r
    import os
    from pathlib import Path
    
    base_time = time.time()
    paths = []
    
    # Генерируем 5 снапшотов
    for i in range(5):
        time.sleep(0.02)
        p = r.snapshot_session(reason=r.REASON_EXIT, cwd=".", recent_cmds=[f"cmd{i}"])
        paths.append(p)

    # Принудительно выставляем mtime ВСЕМ файлам ПОСЛЕ того, как они все созданы
    # Теперь у них гарантированно строгий порядок: i=0 (самый старый), i=4 (самый свежий)
    for i, p in enumerate(paths):
        new_mtime = base_time + (i * 10)
        try:
            os.utime(p, (new_mtime, new_mtime))
        except FileNotFoundError:
            pass

    # Вот теперь вызываем чистильщик, когда на диске идеальный порядок mtime
    r._prune_old_snapshots(keep=3)
    
    # Проверяем, что два самых старых (i=0 и i=1) удалены
    assert not Path(paths[0]).exists()
    assert not Path(paths[1]).exists()
    
    # А три самых свежих (i=2, i=3, i=4) остались
    assert Path(paths[2]).exists()
    assert Path(paths[3]).exists()
    assert Path(paths[4]).exists()

# ============================================================================
# 7. list_recovery_snapshots
# ============================================================================

def test_list_recovery_snapshots_sorted_newest_first(isolated_recovery_dir):
    import time
    import system.recovery as r
    import os
    
    base_time = time.time()
    paths = []
    for i in range(3):
        time.sleep(0.05)  # Пауза ДО создания!
        p = r.snapshot_session(reason=r.REASON_EXIT, cwd=".", recent_cmds=[f"cmd{i}"])
        
        new_mtime = base_time + (i * 10)
        os.utime(p, (new_mtime, new_mtime))
        paths.append(p)
        
    snaps = r.list_recovery_snapshots()
    assert len(snaps) == 3
    # Проверяем, что первый в списке — самый свежий (у него mtime больше всего)
    assert snaps[0]["path"] == paths[-1]

