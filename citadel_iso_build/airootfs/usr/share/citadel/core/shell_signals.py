# FILE: core/shell_signals.py
# Citadel OS — Signal handling для REPL.
#
# Задача: корректно обрабатывать сигналы ОС так, чтобы:
#   1. Ctrl-C (SIGINT) прерывал ТОЛЬКО текущий foreground subprocess, а не весь shell.
#   2. Ctrl-D (EOF) корректно завершал REPL с cleanup'ом.
#   3. SIGTERM/SIGBREAK (Windows) — graceful shutdown.
#   4. SIGWINCH (resize терминала) — обновлял размеры в known state.
#   5. Cleanup фоновых jobs при выходе.
#
# Архитектура:
#   - SignalContext — глобальный singleton, который держит ссылку на текущий
#     foreground Popen (если есть) и при получении SIGINT шлёт ему terminate().
#   - install_handlers() — установить все хендлеры один раз.
#   - register_foreground(proc) / unregister_foreground(proc) — REPL/Pipeline
#     регистрирует текущий процесс перед Popen.wait() и снимает после.
#
# Платформенные нюансы:
#   - На Windows сигналов POSIX нет. Доступны SIGINT, SIGTERM, SIGBREAK, SIGABRT.
#     `os.kill(pid, signal.CTRL_BREAK_EVENT)` работает только для subprocess
#     созданных с creationflags=CREATE_NEW_PROCESS_GROUP.
#   - SIGWINCH на Windows не существует — игнорируем.
#
# Зависимости: только stdlib (signal, os, sys, threading).

from __future__ import annotations

import os
import signal
import sys
import threading
import time
from typing import List, Optional, Set


_IS_WINDOWS = (os.name == "nt")
_SUPPORTS_SIGWINCH = (not _IS_WINDOWS) and hasattr(signal, "SIGWINCH")


class SignalContext:
    """
    Singleton, координирующий signal handlers с текущим foreground subprocess.

    Использование в Pipeline:
        ctx = get_signal_context()
        proc = subprocess.Popen(...)
        ctx.register_foreground(proc)
        try:
            proc.wait()
        finally:
            ctx.unregister_foreground(proc)

    При получении SIGINT (Ctrl-C) SignalContext шлёт SIGTERM/terminate() всем
    зарегистрированным foreground процессам. Если никого нет — пробрасывает
    KeyboardInterrupt в основной поток.
    """

    def __init__(self) -> None:
        self._fg_procs: Set["subprocess.Popen"] = set()
        self._lock = threading.Lock()
        self._installed = False
        self._shutdown_requested = False
        # Храним ссылку на оригинальные обработчики, чтобы восстановить.
        self._original_handlers: dict = {}
        # Колбэки на смену размера терминала (SIGWINCH).
        self._resize_callbacks: List[callable] = []
        # Колбэк на shutdown (SIGTERM).
        self._shutdown_callbacks: List[callable] = []

    # ----- foreground tracking -----

    def register_foreground(self, proc) -> None:
        """Зарегистрировать Popen как текущий foreground процесс."""
        if proc is None:
            return
        with self._lock:
            self._fg_procs.add(proc)

    def register_foreground_many(self, procs) -> None:
        """Зарегистрировать список Popen'ов (для пайпов)."""
        with self._lock:
            self._fg_procs.update(p for p in procs if p is not None)

    def unregister_foreground(self, proc) -> None:
        with self._lock:
            self._fg_procs.discard(proc)

    def unregister_foreground_many(self, procs) -> None:
        with self._lock:
            for p in procs:
                self._fg_procs.discard(p)

    def _get_fg_snapshot(self) -> List:
        with self._lock:
            return [p for p in self._fg_procs if p.poll() is None]

    # ----- installation -----

    def install_handlers(self) -> None:
        """Установить signal handlers. Безопасно звать много раз (no-op после первого)."""
        if self._installed:
            return
        self._installed = True

        # ----- SIGINT (Ctrl-C) -----
        def _sigint_handler(signum, frame):
            # Если есть foreground процесс — шлём ему terminate.
            # Иначе — поднимаем KeyboardInterrupt в основном потоке.
            fgs = self._get_fg_snapshot()
            if fgs:
                for p in fgs:
                    try:
                        p.terminate()
                    except OSError:
                        pass
            else:
                # Печатаем ^C и поднимаем исключение в основном потоке.
                # signal.raise_signal — Python 3.8+, fallback через getframe.
                sys.stderr.write("\n")
                try:
                    import _thread
                    _thread.interrupt_main()
                except Exception:
                    pass

        try:
            self._original_handlers[signal.SIGINT] = signal.signal(
                signal.SIGINT, _sigint_handler,
            )
        except (ValueError, OSError):
            # Not in main thread или платформа не поддерживает.
            pass

        # ----- SIGTERM (graceful shutdown) -----
        def _sigterm_handler(signum, frame):
            self._shutdown_requested = True
            for cb in list(self._shutdown_callbacks):
                try:
                    cb()
                except Exception:
                    pass
            # Прибить все foreground процессы.
            for p in self._get_fg_snapshot():
                try:
                    p.terminate()
                except OSError:
                    pass

        try:
            self._original_handlers[signal.SIGTERM] = signal.signal(
                signal.SIGTERM, _sigterm_handler,
            )
        except (ValueError, OSError):
            pass

        # ----- SIGBREAK (Windows Ctrl-Break) -----
        if _IS_WINDOWS and hasattr(signal, "SIGBREAK"):
            def _sigbreak_handler(signum, frame):
                self._shutdown_requested = True
                for cb in list(self._shutdown_callbacks):
                    try:
                        cb()
                    except Exception:
                        pass
                for p in self._get_fg_snapshot():
                    try:
                        p.terminate()
                    except OSError:
                        pass

            try:
                self._original_handlers[signal.SIGBREAK] = signal.signal(
                    signal.SIGBREAK, _sigbreak_handler,
                )
            except (ValueError, OSError):
                pass

        # ----- SIGWINCH (terminal resize) -----
        if _SUPPORTS_SIGWINCH:
            def _sigwinch_handler(signum, frame):
                for cb in list(self._resize_callbacks):
                    try:
                        cb()
                    except Exception:
                        pass

            try:
                self._original_handlers[signal.SIGWINCH] = signal.signal(
                    signal.SIGWINCH, _sigwinch_handler,
                )
            except (ValueError, OSError):
                pass

    def restore_handlers(self) -> None:
        """Восстановить оригинальные обработчики (для тестов)."""
        for sig, handler in self._original_handlers.items():
            try:
                signal.signal(sig, handler)
            except (ValueError, OSError):
                pass
        self._original_handlers.clear()
        self._installed = False

    # ----- subscription -----

    def on_resize(self, callback) -> None:
        """Подписаться на SIGWINCH (только POSIX)."""
        self._resize_callbacks.append(callback)

    def on_shutdown(self, callback) -> None:
        """Подписаться на SIGTERM/SIGBREAK."""
        self._shutdown_callbacks.append(callback)

    @property
    def shutdown_requested(self) -> bool:
        return self._shutdown_requested

    # ----- cleanup -----

    def cleanup_background(self, job_table=None, *, force: bool = True) -> int:
        """
        Завершить все foreground процессы и (опционально) фоновые jobs.
        Возвращает кол-во прибитых процессов.
        """
        killed = 0
        for p in self._get_fg_snapshot():
            try:
                if force:
                    p.kill()
                else:
                    p.terminate()
                killed += 1
            except OSError:
                pass

        if job_table is not None:
            try:
                killed += job_table.kill_all_running(force=force)
            except Exception:
                pass

        return killed


# ----- singleton -----

_default_ctx: Optional[SignalContext] = None
_default_lock = threading.Lock()


def get_signal_context() -> SignalContext:
    """Ленивый singleton."""
    global _default_ctx
    with _default_lock:
        if _default_ctx is None:
            _default_ctx = SignalContext()
        return _default_ctx


def reset_signal_context() -> None:
    """Сброс (для тестов)."""
    global _default_ctx
    with _default_lock:
        if _default_ctx is not None:
            _default_ctx.restore_handlers()
        _default_ctx = None


def install_handlers() -> SignalContext:
    """Shortcut: установить handlers и вернуть singleton."""
    ctx = get_signal_context()
    ctx.install_handlers()
    return ctx


# ----- хелперы для subprocess -----

def create_subprocess_with_sigint_forwarding(argv, **kwargs) -> "subprocess.Popen":
    """
    Создать subprocess.Popen с автоматической регистрацией в SignalContext,
    чтобы Ctrl-C корректно пробрасывался.

    ВНИМАНИЕ: на Windows для CTRL_BREAK_EVENT нужна creationflags=
    CREATE_NEW_PROCESS_GROUP. По умолчанию используется terminate().
    """
    import subprocess

    # На Windows подмешиваем creationflags для корректной обработки Ctrl-Break.
    if _IS_WINDOWS and "creationflags" not in kwargs:
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    proc = subprocess.Popen(argv, **kwargs)

    ctx = get_signal_context()
    ctx.register_foreground(proc)
    return proc


def terminate_subprocess(proc, *, force: bool = False) -> None:
    """Завершить subprocess и снять его с foreground-регистрации."""
    if proc is None:
        return
    try:
        if force:
            proc.kill()
        else:
            proc.terminate()
    except OSError:
        pass
    finally:
        ctx = get_signal_context()
        ctx.unregister_foreground(proc)
