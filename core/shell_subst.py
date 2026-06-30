# FILE: core/shell_subst.py
# Citadel OS — Command substitution: $(...) и `...`.
#
# Назначение: развернуть подстановки команд в исходной строке ДО лексера
# (т.е. на уровне сырого текста) и подставить их stdout с trim trailing \n.
#
# Поддержка:
#   $(command)          - POSIX-форма
#   `command`           - backticks (legacy)
#   Вложенность:         $(echo $(date))   - обрабатывается рекурсивно
#   Кавычки:             $(echo "hello $USER")  - внутренние ""/'' сохраняются
#                        '$(literal)'           - НЕ подставляется (literal)
#                        "$(echo hi)"           - подставляется (даже в "")
#
# Не подставляется:
#   - Экранированные: \$(cmd) -> literal
#   - Внутри '' (одинарных кавычек)
#
# Конкуренция с subshell-уровнем:
#   В отличие от POSIX-sh, мы НЕ запускаем команды в subshell-окружении.
#   Каждый subshell вызов исполняется как обычный subprocess с capture.
#
# Зависимости: stdlib (subprocess, threading — для параллельности).

from __future__ import annotations

import os
import subprocess
import re
import shlex
import sys
import threading
from typing import List, Optional, Tuple


_MAX_SUBST_DEPTH = 8
_MAX_OUTPUT_BYTES = 1024 * 1024   # 1 MiB safety cap
_SUBST_TIMEOUT = 30.0             # секунд


# ----------------------------------------------------------------------------
# Поиск подстановок: индексы границ и текст команд
# ----------------------------------------------------------------------------

class SubstSpan:
    """Одна найденная подстановка: позиция и тело команды."""

    __slots__ = ("start", "end", "body", "raw_text", "is_backtick")

    def __init__(self, start: int, end: int, body: str,
                 raw_text: str, is_backtick: bool) -> None:
        self.start = start
        self.end = end
        self.body = body
        self.raw_text = raw_text
        self.is_backtick = is_backtick


def find_substitutions(line: str) -> List[SubstSpan]:
    """
    Найти все $(...) и `...` подстановки в строке.

    Возвращает список SubstSpan, отсортированный по start.
    Учитывает кавычки (внутри '' — литерал) и экранирование (\\$).
    """
    spans: List[SubstSpan] = []
    i = 0
    n = len(line)
    in_single = False
    in_double = False

    while i < n:
        ch = line[i]

        # ----- Одинарные кавычки -----
        if ch == "'" and not in_double:
            in_single = not in_single
            i += 1
            continue

        # ----- Двойные кавычки -----
        if ch == '"' and not in_single:
            in_double = not in_double
            i += 1
            continue

        # ----- Внутри одинарных — литерал -----
        if in_single:
            i += 1
            continue

        # ----- Экранирование: \$ или \` -----
        if ch == "\\" and i + 1 < n and line[i + 1] in "$`":
            i += 2
            continue

        # ----- $() -----
        if ch == "$" and i + 1 < n and line[i + 1] == "(":
            start = i
            body, end = _scan_paren(line, i + 1)
            if body is not None:
                # end указывает на позицию после ')'
                spans.append(SubstSpan(
                    start=start, end=end, body=body,
                    raw_text=line[start:end], is_backtick=False,
                ))
                i = end
                continue

        # ----- backticks -----
        if ch == "`":
            start = i
            body, end = _scan_backticks(line, i + 1)
            if body is not None:
                spans.append(SubstSpan(
                    start=start, end=end, body=body,
                    raw_text=line[start:end], is_backtick=True,
                ))
                i = end
                continue

        i += 1

    spans.sort(key=lambda s: s.start)
    return spans


def _scan_paren(line: str, start: int) -> Tuple[Optional[str], int]:
    """
    Сканировать от позиции ПОСЛЕ $( до парной ).
    Учитывает вложенность через баланс скобок и кавычки.
    Вложенные $( и ` тоже считаются по скобкам (т.е. сначала смотрим
    только на баланс `(` и `)`, а вложенные команды мы обработаем
    в следующем проходе perform_substitution).
    Возвращает (body, end_index) или (None, start) при ошибке.
    """
    if start >= len(line) or line[start] != "(":
        return None, start

    depth = 1
    i = start + 1
    in_single = False
    in_double = False

    while i < len(line):
        ch = line[i]

        if in_single:
            if ch == "'":
                in_single = False
            i += 1
            continue

        if in_double:
            if ch == '"':
                in_double = False
            elif ch == "\\" and i + 1 < len(line):
                i += 2
                continue
            i += 1
            continue

        if ch == "'":
            in_single = True
        elif ch == '"':
            in_double = True
        elif ch == "\\" and i + 1 < len(line):
            # Пропускаем escape-последовательность.
            i += 2
            continue
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return line[start + 1:i], i + 1

        i += 1

    return None, start   # unmatched


def _scan_backticks(line: str, start: int) -> Tuple[Optional[str], int]:
    """
    Сканировать от позиции после ` до парного `.
    Учитывает кавычки и экранирование. Вложенные $(/`, если встретятся
    внутри — будут обработаны в следующих проходах perform_substitution().
    """
    i = start
    in_single = False
    in_double = False

    while i < len(line):
        ch = line[i]

        if in_single:
            if ch == "'":
                in_single = False
            i += 1
            continue

        if in_double:
            if ch == '"':
                in_double = False
            elif ch == "\\" and i + 1 < len(line):
                i += 2
                continue
            i += 1
            continue

        if ch == "'":
            in_single = True
            i += 1
            continue
        if ch == '"':
            in_double = True
            i += 1
            continue
        if ch == "\\" and i + 1 < len(line):
            if line[i + 1] == "`":
                i += 2
                continue
            # Прочие escapes: пропускаем два символа.
            i += 2
            continue
        if ch == "`":
            return line[start:i], i + 1

        i += 1

    return None, start


# ----------------------------------------------------------------------------
# Выполнение команды
# ----------------------------------------------------------------------------

def _run_capture(cmd: str, *, env: Optional[dict] = None) -> str:
    """
    Выполнить команду и вернуть stdout (с trim trailing \n).

    Использует shell=False (shlex.split) для безопасности, но позволяет
    вызывать builtin'ы Citadel через `citadel-cmd` обёртку.
    """
    # Попробуем распарсить как shell-like, но безопасно.
    try:
        argv = shlex.split(cmd)
    except ValueError:
        argv = cmd.split()

    if not argv:
        return ""

    # Если команда — это путь к бинарю или алиас: используем прямой запуск.
    # На Windows: где `python` итд есть.
    try:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env if env is not None else os.environ.copy(),
            text=False,
        )
    except FileNotFoundError:
        return ""
    except OSError:
        return ""

    try:
        stdout, stderr = proc.communicate(timeout=_SUBST_TIMEOUT)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except OSError:
            pass
        return ""

    if len(stdout) > _MAX_OUTPUT_BYTES:
        stdout = stdout[:_MAX_OUTPUT_BYTES]

    text = stdout.decode("utf-8", errors="replace")
    # POSIX: trim один trailing newline (или CRLF).
    if text.endswith("\r\n"):
        text = text[:-2]
    elif text.endswith("\n"):
        text = text[:-1]
    return text


# ----------------------------------------------------------------------------
# Главная функция подстановки
# ----------------------------------------------------------------------------

def perform_substitution(
    line: str,
    *,
    env: Optional[dict] = None,
    max_depth: int = _MAX_SUBST_DEPTH,
) -> str:
    """
    Развернуть все $(...) и `...` в строке, рекурсивно до max_depth.
    Возвращает новую строку с подставленными значениями.

    Кавычки и экранирование в исходной строке УЧИТЫВАЮТСЯ:
        echo $(echo hi)         -> "echo hi"
        echo '$(echo hi)'       -> "echo $(echo hi)"  (literal, в '')
        echo $(echo hi)         -> "echo $(echo hi)"  (escaped)
    """
    depth = 0
    current = line
    while depth < max_depth:
        spans = find_substitutions(current)
        if not spans:
            break

        # Обрабатываем СПРАВА НАЛЕВО, чтобы не сбивать индексы.
        new_parts: List[str] = []
        prev_end = 0

        for span in reversed(spans):
            # Подставляем результат команды.
            result = _run_capture(span.body, env=env)
            new_parts.append(result)
            new_parts.append(current[prev_end:span.start])
            prev_end = span.end

        new_parts.append(current[prev_end:])
        new_parts.reverse()
        current = "".join(new_parts)
        depth += 1

    return current


# ----------------------------------------------------------------------------
# Хелпер: безопасная подстановка с логированием ошибок
# ----------------------------------------------------------------------------

def safe_substitute(line: str, *, env: Optional[dict] = None) -> str:
    """
    Обёртка: при любой ошибке возвращает исходную строку.
    Используется в hot path run_command().
    """
    if "$(" not in line and "`" not in line:
        return line
    try:
        return perform_substitution(line, env=env)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"citadel: substitution error: {e}\n")
        return line


# ----------------------------------------------------------------------------
# Self-test
# ----------------------------------------------------------------------------

if __name__ == "__main__":
    # Базовые проверки парсинга.
    DOLLAR = "$"   # чтобы избежать SyntaxWarning на \$
    tests = [
        (f"echo {DOLLAR}(date)",            True),
        ("echo `date`",                     True),
        (f"echo '{DOLLAR}(date)'",          False),
        (f'echo "{DOLLAR}(date)"',          True),
        (f"echo {DOLLAR}(echo {DOLLAR}(date))",    True),
        (rf"echo \{DOLLAR}(date)",          False),
        ("echo 'no sub here'",              False),
        (f"{DOLLAR}(echo a) {DOLLAR}(echo b)",     True),
    ]
    for s, should_find in tests:
        spans = find_substitutions(s)
        found = bool(spans)
        ok = (found == should_find)
        marker = "OK" if ok else "FAIL"
        print(f"  [{marker}] {s!r:35}  spans={len(spans)}  expect={should_find}")
        for sp in spans:
            print(f"        -> body={sp.body!r}  raw={sp.raw_text!r}")
