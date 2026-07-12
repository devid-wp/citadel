# FILE: core/shell_pipeline.py
# Citadel OS — Pipeline + Redirection Engine.
#
# Задача: превратить список токенов (от Tokenizer + VariableStore + AliasEngine)
# в список PipelineStage'ов и выполнить их через subprocess.Popen с реальными
# file descriptors и пайпами между процессами.
#
# Поддерживаемые конструкции:
#   cmd1 | cmd2                    — stdout cmd1 → stdin cmd2
#   cmd1 |& cmd2                   — stdout + stderr cmd1 → stdin cmd2
#   cmd > file                     — перезаписать
#   cmd >> file                    — дописать
#   cmd < file                     — читать stdin из файла
#   cmd 2> file                    — stderr в файл
#   cmd 2>&1                       — stderr в тот же fd что и stdout
#   cmd > file 2>&1                — оба потока в файл
#   cmd1 ; cmd2                    — последовательно (отдельные вызовы)
#   cmd &                          — выполнить в фоне (fire-and-forget)
#
# Семантика POSIX-ish, но упрощённая: job control (fg/bg, Ctrl-Z) пока нет —
# `&` просто запускает detached-процесс.
#
# Зависимости: только stdlib (subprocess, os, threading).

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .shell_tokenizer import Token, is_redirection, is_control
from .shell_jobs import (
    BackgroundJob, JobTable, run_stages_in_background,
    get_default_job_table,
)


# ============================================================================
# Структуры данных
# ============================================================================

@dataclass
class Redirection:
    """Один редирект (один из >, >>, <, 2>, 2>&1)."""
    kind: str                # "out" | "app" | "in" | "err" | "merge"
    target: Optional[str]    # путь к файлу (для merge=None)

    def open(self):
        """Открыть файл как fd (или вернуть существующий fd для merge)."""
        if self.kind == "out":
            return open(self.target or "/dev/null", "w", encoding="utf-8", errors="replace")
        if self.kind == "app":
            return open(self.target or "/dev/null", "a", encoding="utf-8", errors="replace")
        if self.kind == "in":
            return open(self.target or "/dev/null", "r", encoding="utf-8", errors="replace")
        # merge/err handled via fileno(), здесь не открываем
        return None


@dataclass
class PipelineStage:
    """Один сегмент между `|` (или самостоятельная команда)."""
    argv: List[str]
    stdin: Optional[Redirection] = None
    stdout: Optional[Redirection] = None
    stderr: Optional[Redirection] = None
    background: bool = False


@dataclass
class ParsedCommand:
    """Результат парсинга одного `;`-сегмента (цепочка пайпов)."""
    stages: List[PipelineStage] = field(default_factory=list)


class PipelineError(Exception):
    """Парсинг упал (несбалансированные пайпы, редирект без файла и т.п.)."""


# ============================================================================
# Парсинг
# ============================================================================

def parse_pipeline(tokens: List[Token]) -> List[PipelineStage]:
    """
    Разобрать плоский список токенов в список PipelineStage.

    Raises:
        PipelineError: если синтаксис сломан (нет файла после >, нет команды
        после | и т.п.).
    """
    if not tokens:
        return []

    stages: List[PipelineStage] = []
    current = PipelineStage(argv=[])
    pending_stdin_err: Optional[str] = None   # неиспользованный stderr-редирект ("2>")
    pending_stdin_merge: bool = False         # неиспользованный 2>&1

    i = 0
    while i < len(tokens):
        tok = tokens[i]

        # ----- Разделители пайпов -----
        if tok.kind == "pipe":
            if not current.argv:
                raise PipelineError(f"Pipe `|` without command at token #{i}")
            stages.append(current)
            current = PipelineStage(argv=[])
            pending_stdin_err = None
            pending_stdin_merge = False
            i += 1
            continue

        if tok.kind == "pipe_err":
            # |& — следующий stage получит и stdout, и stderr.
            if not current.argv:
                raise PipelineError(f"Pipe `|&` without command at token #{i}")
            current.stderr = Redirection(kind="merge", target=None)  # type: ignore[assignment]
            stages.append(current)
            current = PipelineStage(argv=[])
            pending_stdin_err = None
            pending_stdin_merge = False
            i += 1
            continue

        if tok.kind == "background":
            current.background = True
            i += 1
            continue

        if tok.kind == "semicolon":
            # `;` разделяет команды, но в рамках одной строки REPL мы обрабатываем
            # их по одной. Парсер `;`-сегментов — на уровень выше.
            # Здесь мы просто отдаём текущий stages и сбрасываем current.
            if current.argv:
                stages.append(current)
                current = PipelineStage(argv=[])
            pending_stdin_err = None
            pending_stdin_merge = False
            i += 1
            continue

        # ----- Редиректы -----
        if tok.kind in ("redir_out", "redir_app", "redir_in"):
            target = _expect_word(tokens, i + 1, tok.value)
            r = Redirection(
                kind={"redir_out": "out", "redir_app": "app", "redir_in": "in"}[tok.kind],
                target=target.value,
            )
            if tok.kind == "redir_out":
                current.stdout = r
            elif tok.kind == "redir_app":
                current.stdout = r
            else:
                current.stdin = r
            i += 2
            continue

        if tok.kind == "redir_err":
            target = _expect_word(tokens, i + 1, tok.value)
            current.stderr = Redirection(kind="err", target=target.value)
            pending_stdin_err = target.value
            i += 2
            continue

        if tok.kind == "redir_merge":
            # 2>&1 — stderr уходит туда же, куда и stdout.
            current.stderr = Redirection(kind="merge", target=None)
            pending_stdin_merge = True
            i += 1
            continue

        # ----- Обычное слово -----
        current.argv.append(tok.value)
        i += 1

    if current.argv:
        stages.append(current)

    if not stages:
        raise PipelineError("Empty pipeline")

    return stages


def _expect_word(tokens: List[Token], idx: int, op: str) -> Token:
    """После оператора редиректа должно идти слово (путь к файлу)."""
    if idx >= len(tokens):
        raise PipelineError(f"Redirection `{op}` without target")
    nxt = tokens[idx]
    if nxt.kind != "word":
        raise PipelineError(
            f"Expected filename after `{op}`, got `{nxt.value}` ({nxt.kind})"
        )
    return nxt


# ============================================================================
# Исполнение
# ============================================================================

def execute_pipeline(
    stages: List[PipelineStage],
    *,
    env: Optional[dict] = None,
    cwd: Optional[str] = None,
    on_line: Optional[callable] = None,
) -> int:
    """
    Выполнить цепочку пайпов.

    Args:
        stages: список PipelineStage от parse_pipeline().
        env: переменные окружения (обычно VariableStore.as_env()).
        cwd: рабочая директория (None = текущая).
        on_line: колбэк line -> None, вызывается для каждой строки stdout
                 последнего stage (для live-tail эффекта).

    Returns:
        Exit code последнего процесса в пайпе.
    """
    if not stages:
        return 0

    processes: List[subprocess.Popen] = []
    open_fds: List = []           # чтобы закрыть после использования

    try:
        prev_stdout = None        # fd, который передаётся следующему stage как stdin

        for i, stage in enumerate(stages):
            is_last = (i == len(stages) - 1)

            # ----- stdin -----
            if prev_stdout is not None:
                stdin_fd = prev_stdout
            elif stage.stdin is not None:
                stdin_fd = stage.stdin.open()
                if stdin_fd is not None:
                    open_fds.append(stdin_fd)
            else:
                stdin_fd = None   # унаследовать от родителя

            # ----- stdout -----
            if is_last and stage.stdout is None and on_line is None:
                stdout_fd = None  # inherit — пользователь видит в терминале
            elif is_last and on_line is not None and stage.stdout is None:
                # Перехватываем stdout чтобы стримить через on_line.
                stdout_fd = subprocess.PIPE
            elif stage.stdout is not None:
                stdout_fd = stage.stdout.open()
                if stdout_fd is not None:
                    open_fds.append(stdout_fd)
            else:
                # Не последний stage — обязательно нужен PIPE для передачи дальше.
                stdout_fd = subprocess.PIPE

            # ----- stderr -----
            if stage.stderr is None:
                stderr_fd = None
            elif stage.stderr.kind == "merge":
                # 2>&1: stderr уходит туда же, куда и stdout.
                # Если stdout = None (inherit), то и stderr inherit.
                stderr_fd = stdout_fd
            elif stage.stderr.kind == "err":
                stderr_fd = stage.stderr.open()
                if stderr_fd is not None:
                    open_fds.append(stderr_fd)
            else:
                stderr_fd = None

            # ----- Запуск -----
            try:
                # Гарантируем unbuffered вывод для Python subprocess'ов
                # чтобы данные не терялись когда родитель уже закрыл pipe.
                proc_env = env
                if env is not None and stage.argv and stage.argv[0]:
                    head = stage.argv[0].lower()
                    if (head.endswith("python") or head.endswith("python.exe")
                            or "/python" in head or "\\python" in head
                            or "py" == os.path.basename(head)):
                        proc_env = dict(env)
                        proc_env.setdefault("PYTHONUNBUFFERED", "1")
                proc = subprocess.Popen(
                    stage.argv,
                    stdin=stdin_fd,
                    stdout=stdout_fd,
                    stderr=stderr_fd,
                    env=proc_env,
                    cwd=cwd,
                    text=False,            # bytes для универсальности; on_line сам декодит
                )
            except FileNotFoundError as e:
                raise PipelineError(f"Command not found: {stage.argv[0]}") from e
            except PermissionError as e:
                raise PipelineError(f"Permission denied: {stage.argv[0]}") from e
            except OSError as e:
                raise PipelineError(f"OS error running {stage.argv[0]}: {e}") from e

            # Если мы передали prev_stdout как stdin — в дочернем он уже дублирован,
            # родительский fd нам больше не нужен.
            if prev_stdout is not None and prev_stdout not in (subprocess.PIPE, None):
                try:
                    prev_stdout.close()
                except OSError:
                    pass
                if prev_stdout in open_fds:
                    open_fds.remove(prev_stdout)

            processes.append(proc)
            prev_stdout = proc.stdout if isinstance(proc.stdout, int) else proc.stdout

        # ----- Финальная обработка -----
        last_proc = processes[-1]

        if on_line is not None and isinstance(last_proc.stdout, subprocess.Popen.__class__):
            # Стримим stdout последнего stage построчно.
            _stream_lines(last_proc, on_line)

        # Если пайп — закрываем stdin последнему (чтобы он не висел на EOF).
        if last_proc.stdin and last_proc.stdin not in (None, subprocess.PIPE):
            try:
                last_proc.stdin.close()
            except OSError:
                pass

        # Ждём всех
        for proc in processes:
            try:
                proc.wait()
            except KeyboardInterrupt:
                # Ctrl-C в REPL — прибиваем весь пайп.
                for p in processes:
                    try:
                        p.terminate()
                    except OSError:
                        pass
                raise

        return processes[-1].returncode if processes[-1].returncode is not None else -1

    finally:
        for fd in open_fds:
            try:
                fd.close()
            except OSError:
                pass


def _stream_lines(proc: subprocess.Popen, on_line: callable) -> None:
    """Читать stdout процесса построчно и звать on_line(str)."""
    if proc.stdout is None:
        return

    def _reader():
        try:
            for raw in iter(proc.stdout.readline, b""):
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").rstrip("\n")
                try:
                    on_line(line)
                except Exception:
                    pass
        finally:
            try:
                proc.stdout.close()
            except OSError:
                pass

    t = threading.Thread(target=_reader, daemon=True)
    t.start()
    # НЕ ждём t здесь — пускай крутится параллельно с proc.wait().
    # proc.wait() в execute_pipeline дождётся завершения самого процесса.


# ============================================================================
# Высокоуровневый API: разбить строку по `;` и выполнить каждую команду
# ============================================================================

def _split_by(
    tokens: List[Token],
    kinds: tuple,
) -> List[List[Token]]:
    """Разбить плоский список токенов на сегменты по операторам kinds."""
    segments: List[List[Token]] = [[]]
    for tok in tokens:
        if tok.kind in kinds:
            if segments[-1]:
                segments.append([])
        else:
            segments[-1].append(tok)
    return [s for s in segments if s]


def _last_exit_of_segment(
    segment: List[Token],
    *,
    env: Optional[dict],
    cwd: Optional[str],
    on_line: Optional[callable],
    raw_command: str = "",
) -> int:
    """Выполнить один сегмент (цепочку пайпов) и вернуть exit code.

    Если в сегменте есть stage с background=True — запускаем через JobTable
    и сразу возвращаем 0 (фоновый job не должен блокировать).
    """
    if not segment:
        return 0
    try:
        stages = parse_pipeline(segment)
    except PipelineError as e:
        sys.stderr.write(f"citadel: parse error: {e}\n")
        return 2

    # Проверка: есть ли хотя бы один background stage.
    has_background = any(s.background for s in stages)

    if has_background:
        # Запускаем через JobTable.
        job_table = get_default_job_table()
        job = run_stages_in_background(
            job_table, stages, raw_command or "background job",
            cwd=cwd, env=env, on_line=on_line,
        )
        # Сообщаем пользователю.
        print(
            f"  [{job.job_id}] {job.pid}  {raw_command or '(background)'}",
            file=sys.stderr,
        )
        return 0

    try:
        return execute_pipeline(stages, env=env, cwd=cwd, on_line=on_line)
    except PipelineError as e:
        sys.stderr.write(f"citadel: {e}\n")
        return 127


def execute_commandline(
    tokens: List[Token],
    *,
    env: Optional[dict] = None,
    cwd: Optional[str] = None,
    on_line: Optional[callable] = None,
    raw_command: str = "",
) -> int:
    """
    Выполнить список токенов с учётом ;, &&, ||.

    Приоритет операторов (от высшего к низшему):
        1. && и ||   — short-circuit внутри одной логической цепочки
        2. ;         — разделитель независимых команд (всегда выполняются)

    Returns:
        Exit code последней выполненной команды.
    """
    if not tokens:
        return 0

    # ----- Сборка плоского списка "подкоманда + оператор" -----
    # Разбиваем по ; на независимые команды.
    # Затем внутри каждой команды разделяем по && и ||.
    # Идём слева направо, применяя short-circuit.
    raw_segments = _split_by(tokens, ("semicolon",))

    last_exit = 0
    for raw_seg in raw_segments:
        if not raw_seg:
            continue

        # Внутри raw_seg выделяем последовательность (cmd, op, cmd, op, cmd).
        # Пары собираем: cond_segments — список [(cmd_tokens, op_to_next), ...].
        cond_segments = _split_by(raw_seg, ("and", "or"))
        if not cond_segments:
            continue

        # Строим явный список с операторами между сегментами.
        items: List = []  # [(tokens, op_to_next)]  op_to_next = "and" | "or" | None
        op_iter = iter(_collect_operators_between(raw_seg, ("and", "or")))
        for cmd_tokens in cond_segments:
            op = next(op_iter, None)
            items.append((cmd_tokens, op))

        # Выполняем с правильной POSIX-семантикой и приоритетом && над ||.
        last_exit = _parse_conditional_chain(
            items, env, cwd, on_line, raw_command=raw_command,
        )

    return last_exit


def _collect_operators_between(
    tokens: List[Token],
    kinds: tuple,
) -> List[str]:
    """Вернуть список операторов kinds, которые встречаются между word-токенами."""
    out: List[str] = []
    for tok in tokens:
        if tok.kind in kinds:
            out.append(tok.kind)
    return out


def _parse_conditional_chain(
    items: List,
    env: Optional[dict],
    cwd: Optional[str],
    on_line: Optional[callable],
    raw_command: str = "",
) -> int:
    """
    Вычислить цепочку [(cmd_tokens, op)] с POSIX-семантикой коротких замыканий.

    POSIX-правила (ассоциативность слева, && и || равноправны):
        A && B   → выполни A; если rc=0, выполни B; иначе rc=rc_A, B skip
        A || B   → выполни A; если rc≠0, выполни B; иначе rc=rc_A, B skip

    Для смешанных: `A && B || C` = `((A && B) || C)` (одинаковый приоритет).
    Это эквивалентно left-to-right state-machine.
    """
    last_exit = 0
    skip_next = False       # skip следующий cmd?

    for cmd_tokens, op in items:
        if skip_next:
            # Правый операнд skip'нут. Выходим из skip-режима,
            # но НЕ выполняем cmd — POSIX: exit остаётся от left.
            skip_next = False
            continue

        last_exit = _last_exit_of_segment(
            cmd_tokens, env=env, cwd=cwd, on_line=on_line,
            raw_command=raw_command,
        )

        if op == "and" and last_exit != 0:
            skip_next = True   # skip правый операнд
        elif op == "or" and last_exit == 0:
            skip_next = True   # skip правый операнд

    return last_exit