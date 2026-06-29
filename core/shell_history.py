# FILE: core/shell_history.py
# Citadel OS — История команд (History Manager).
#
# Архитектура:
#   - В RAM: collections.deque(maxlen=MAX_RAM) — последние N команд.
#   - На диске: ~/.citadel_history (JSONL) — append-only, по строке на команду.
#   - При старте сессии подгружаем последние DISK_LOAD записей с диска.
#
# Что хранится в каждой записи:
#   ts           — epoch (float, секунды)
#   cmd          — сырая команда (до токенизации, до алиасов)
#   cwd          — рабочая директория на момент выполнения
#   exit_code    — код возврата последнего процесса в пайпе
#   duration_ms  — время выполнения в миллисекундах
#
# Потокобезопасность: lock вокруг операций с deque + append к файлу.
# Shell REPL однопоточный, но HistoryManager могут дёргать фоновые
# модули (HUD, например) — поэтому защищаемся.

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Deque, List, Optional


# ----- Tunables ---------------------------------------------------------------

MAX_RAM = 500              # размер кольца в памяти
DISK_LOAD = 500            # сколько последних строк подгружать при старте
HISTORY_FILE = os.path.join(
    os.path.expanduser("~"), ".citadel_history",
)


# ----- Data -------------------------------------------------------------------

@dataclass
class HistoryEntry:
    ts: float = 0.0
    cmd: str = ""
    cwd: str = ""
    exit_code: int = 0
    duration_ms: int = 0


@dataclass
class _PendingRecord:
    """
    Запись, которая ещё выполняется. После завершения превращается в HistoryEntry.
    Нужно чтобы замерить duration_ms и поймать exit_code.
    """
    started_at: float
    cmd: str
    cwd: str


# ----- Manager ---------------------------------------------------------------

class HistoryManager:
    """
    Хранит историю команд Citadel OS.

    Использование:
        hist = HistoryManager()
        token = hist.begin("ls -la /etc")
        ... выполнение ...
        hist.finish(token, exit_code=0)

        for entry in hist.recent(20):
            print(entry.cmd)
    """

    def __init__(
        self,
        history_path: Optional[str] = None,
        max_ram: int = MAX_RAM,
        disk_load: int = DISK_LOAD,
    ) -> None:
        self._path = history_path or HISTORY_FILE
        self._ring: Deque[HistoryEntry] = deque(maxlen=max_ram)
        self._lock = threading.Lock()
        self._disk_load = disk_load
        self._ensure_file()
        self._load_from_disk()

    # ------------------------------------------------------------------
    # Файловые операции
    # ------------------------------------------------------------------
    def _ensure_file(self) -> None:
        """Создать файл истории если его нет (с безопасными правами)."""
        if os.path.exists(self._path):
            return
        try:
            os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
            with open(self._path, "a", encoding="utf-8"):
                pass
            # POSIX: история не должна быть world-readable (там бывают пароли).
            try:
                os.chmod(self._path, 0o600)
            except (OSError, AttributeError):
                pass
        except OSError:
            # Если не можем создать — работаем только в RAM, без падения.
            self._path = ""

    def _load_from_disk(self) -> None:
        """Подгрузить последние N записей с диска в RAM-кольцо."""
        if not self._path or not os.path.exists(self._path):
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                # tail-семантика: читаем всё, берём последние disk_load строк.
                lines = f.readlines()[-self._disk_load:]
            for raw in lines:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                    entry = HistoryEntry(
                        ts=float(data.get("ts", 0.0)),
                        cmd=str(data.get("cmd", "")),
                        cwd=str(data.get("cwd", "")),
                        exit_code=int(data.get("exit_code", 0)),
                        duration_ms=int(data.get("duration_ms", 0)),
                    )
                    self._ring.append(entry)
                except (json.JSONDecodeError, ValueError, TypeError):
                    # Битая строка в истории — пропускаем, не валим shell.
                    continue
        except OSError:
            pass

    def _append_to_disk(self, entry: HistoryEntry) -> None:
        """Дописать запись в конец JSONL-файла."""
        if not self._path:
            return
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
        except OSError:
            # Не можем записать — окей, история только в RAM.
            pass

    # ------------------------------------------------------------------
    # Публичное API
    # ------------------------------------------------------------------
    def begin(self, cmd: str) -> _PendingRecord:
        """
        Начать выполнение команды. Возвращает токен, который нужно
        передать в finish() после завершения.
        """
        record = _PendingRecord(
            started_at=time.time(),
            cmd=cmd,
            cwd=os.getcwd(),
        )
        return record

    def finish(self, record: _PendingRecord, exit_code: int = 0) -> HistoryEntry:
        """
        Завершить выполнение команды. Записывает в RAM и на диск.
        Возвращает получившуюся запись.
        """
        if record is None:
            return HistoryEntry()
        duration_ms = int((time.time() - record.started_at) * 1000)
        entry = HistoryEntry(
            ts=record.started_at,
            cmd=record.cmd,
            cwd=record.cwd,
            exit_code=int(exit_code),
            duration_ms=duration_ms,
        )
        with self._lock:
            self._ring.append(entry)
            self._append_to_disk(entry)
        return entry

    def record_inline(self, cmd: str, exit_code: int, duration_ms: int) -> HistoryEntry:
        """
        Записать команду без пары begin/finish (для синхронных builtin-команд,
        которые сами знают свой exit_code).
        """
        entry = HistoryEntry(
            ts=time.time(),
            cmd=cmd,
            cwd=os.getcwd(),
            exit_code=int(exit_code),
            duration_ms=int(duration_ms),
        )
        with self._lock:
            self._ring.append(entry)
            self._append_to_disk(entry)
        return entry

    def recent(self, n: int = 20) -> List[HistoryEntry]:
        """Последние N записей (новейшие первые)."""
        with self._lock:
            items = list(self._ring)
        items.reverse()
        return items[: max(0, n)]

    def all(self) -> List[HistoryEntry]:
        """Полный снимок истории (для экспорта/дампa)."""
        with self._lock:
            return list(self._ring)

    def search(self, substring: str, limit: int = 20) -> List[HistoryEntry]:
        """Простой поиск по подстроке (новейшие первые)."""
        if not substring:
            return self.recent(limit)
        needle = substring.lower()
        with self._lock:
            items = list(self._ring)
        out = [e for e in reversed(items) if needle in e.cmd.lower()]
        return out[: max(0, limit)]

    def clear(self) -> None:
        """Очистить RAM-кольцо (на диске остаётся)."""
        with self._lock:
            self._ring.clear()

    def truncate_disk(self) -> bool:
        """Полностью стереть файл истории на диске."""
        if not self._path:
            return False
        try:
            with open(self._path, "w", encoding="utf-8"):
                pass
            return True
        except OSError:
            return False


# ----- Singleton --------------------------------------------------------------

_default_history: Optional[HistoryManager] = None


def get_default_history() -> HistoryManager:
    """Ленивый singleton — основной менеджер истории сессии."""
    global _default_history
    if _default_history is None:
        _default_history = HistoryManager()
    return _default_history