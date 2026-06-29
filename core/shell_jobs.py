# FILE: core/shell_jobs.py
# Citadel OS — Job Control для фоновых процессов.
#
# Архитектура:
#   - Каждый фоновый job — это BackgroundPipeline (subprocess.Popen list + state).
#   - JobTable — глобальный реестр активных и завершённых jobs.
#   - При выполнении `cmd &` сразу возвращаем управление, job регистрируется в таблице.
#   - Периодически (или при вызове jobs/jobs -l) обновляем статусы: running/exited.
#
# Поддерживаемые операции:
#   - run_in_background(stages) → (job_id, pid)
#   - wait(job_id, timeout=None) — дождаться завершения
#   - kill(job_id, sig=SIGTERM)
#   - list_jobs() — список всех jobs (running + exited, недавно)
#   - cleanup() — удалить завершённые jobs из таблицы
#
# POSIX vs Windows:
#   - На Linux job_id = "%1", "%2" ...
#   - На Windows просто числовой ID.
#   - Сигналы: Popen.terminate() работает обеих платформах.

from __future__ import annotations

import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class JobState(str, Enum):
    RUNNING = "running"
    EXITED = "exited"
    KILLED = "killed"


@dataclass
class BackgroundJob:
    """Фоновый job — один PipelineStage или цепочка пайпов."""

    job_id: int
    pid: int
    command: str           # для отображения (например, "sleep 10")
    pipeline_args: List[List[str]] = field(default_factory=list)   # [[stage1 argv], [stage2 argv]]
    processes: List[subprocess.Popen] = field(default_factory=list)
    state: JobState = JobState.RUNNING
    exit_code: Optional[int] = None
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None

    def is_alive(self) -> bool:
        """Жив ли ещё хоть один процесс в пайпе."""
        return any(p.poll() is None for p in self.processes)

    def refresh_state(self) -> None:
        """Обновить state/exit_code на основе subprocess.poll()."""
        if self.state != JobState.RUNNING:
            return
        if not self.is_alive():
            # Последний poll — берём exit_code последнего процесса.
            self.exit_code = self.processes[-1].returncode if self.processes else -1
            self.state = JobState.EXITED
            self.ended_at = time.time()


class JobTable:
    """
    Реестр фоновых jobs с автообновлением статусов.
    Потокобезобасно (Lock вокруг мутаций).
    """

    MAX_KEEP_EXITED = 50     # хранить не более N завершённых jobs

    def __init__(self) -> None:
        self._jobs: Dict[int, BackgroundJob] = {}
        self._next_id: int = 1
        self._lock = threading.Lock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._jobs)

    def add(self, job: BackgroundJob) -> int:
        """Зарегистрировать новый job, вернуть его ID."""
        with self._lock:
            # Поскольку job уже создан с конкретным ID, используем его.
            self._jobs[job.job_id] = job
            self._cleanup_exited()
            return job.job_id

    def allocate_id(self) -> int:
        """Зарезервировать новый уникальный ID для job."""
        with self._lock:
            jid = self._next_id
            self._next_id += 1
            return jid

    def _cleanup_exited(self) -> None:
        """Удалить лишние завершённые jobs (старые)."""
        exited = [j for j in self._jobs.values() if j.state == JobState.EXITED]
        if len(exited) <= self.MAX_KEEP_EXITED:
            return
        # Сортировка: последние выше, удаляем хвост
        exited.sort(key=lambda j: j.ended_at or 0.0)
        to_remove = exited[: len(exited) - self.MAX_KEEP_EXITED]
        for j in to_remove:
            self._jobs.pop(j.job_id, None)

    def get(self, job_id: int) -> Optional[BackgroundJob]:
        with self._lock:
            return self._jobs.get(job_id)

    def all(self) -> List[BackgroundJob]:
        """Снимок всех jobs (новейшие первые)."""
        with self._lock:
            self._refresh_states()
            items = list(self._jobs.values())
        items.sort(key=lambda j: j.job_id, reverse=True)
        return items

    def running(self) -> List[BackgroundJob]:
        """Только активные jobs."""
        with self._lock:
            self._refresh_states()
            items = [j for j in self._jobs.values() if j.state == JobState.RUNNING]
        items.sort(key=lambda j: j.job_id, reverse=True)
        return items

    def _refresh_states(self) -> None:
        """Обновить state всех running jobs."""
        for j in self._jobs.values():
            if j.state == JobState.RUNNING:
                j.refresh_state()

    def kill(self, job_id: int, *, force: bool = False) -> bool:
        """Завершить job. Возвращает True если найден."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.state != JobState.RUNNING:
                return False
            for p in job.processes:
                try:
                    if force:
                        p.kill()
                    else:
                        p.terminate()
                except OSError:
                    pass
            job.state = JobState.KILLED
            job.ended_at = time.time()
        return True

    def wait(self, job_id: int, timeout: Optional[float] = None) -> Optional[int]:
        """Дождаться завершения job. Возвращает exit_code или None по таймауту."""
        job = self.get(job_id)
        if job is None:
            return None
        deadline = (time.time() + timeout) if timeout else None

        while job.is_alive():
            if deadline and time.time() > deadline:
                return None
            time.sleep(0.05)

        job.refresh_state()
        return job.exit_code


# ----- Запуск фонового pipeline -----

def run_stages_in_background(
    job_table: JobTable,
    stages,                    # List[PipelineStage] от parse_pipeline()
    command: str,
    *,
    cwd: Optional[str] = None,
    env: Optional[dict] = None,
    on_line=None,
) -> BackgroundJob:
    """
    Запустить цепочку пайпов в фоне. Возвращает BackgroundJob.

    Эта функция создаёт НЕСВЯЗАННЫЕ процессы (subprocess.Popen без wait()),
    без блокировки основного потока. stdin = DEVNULL, stdout/stderr могут
    быть либо унаследованы (видны в терминале родителя), либо PIPE (для
    live-stream через on_line).
    """
    jid = job_table.allocate_id()
    processes: List[subprocess.Popen] = []
    pipe_stages: Dict[int, subprocess.Popen] = {}   # pid -> prev stage (для stdin)

    prev_stdout = None
    for i, stage in enumerate(stages):
        is_last = (i == len(stages) - 1)

        # stdin: либо пайп от прошлого stage, либо DEVNULL
        if prev_stdout is not None:
            stdin_fd: object = prev_stdout
        else:
            stdin_fd = subprocess.DEVNULL

        # stdout: для background процессов — DEVNULL (иначе засорим терминал),
        # кроме случая когда передан on_line и это последний stage.
        if is_last and on_line is not None:
            stdout_fd = subprocess.PIPE
        else:
            stdout_fd = subprocess.DEVNULL

        stderr_fd = subprocess.STDOUT if on_line and is_last else subprocess.DEVNULL

        proc = subprocess.Popen(
            stage.argv,
            stdin=stdin_fd,
            stdout=stdout_fd,
            stderr=stderr_fd,
            env=env,
            cwd=cwd,
            text=False,
        )
        processes.append(proc)

        # Передать stdout текущего → stdin следующего через fileno
        if isinstance(prev_stdout, int):
            try:
                os.close(prev_stdout)
            except OSError:
                pass

        if isinstance(proc.stdout, int):
            prev_stdout = proc.stdout
        else:
            prev_stdout = None

    job = BackgroundJob(
        job_id=jid,
        pid=processes[0].pid if processes else -1,
        command=command,
        pipeline_args=[s.argv for s in stages],
        processes=processes,
    )
    job_table.add(job)

    # Опционально: поток, который читает вывод последнего stage и зовёт on_line.
    if on_line is not None and processes:
        last = processes[-1]
        if isinstance(last.stdout, int):

            def _bg_reader():
                try:
                    with os.fdopen(last.stdout, "rb", closefd=False) as f:
                        for raw in iter(f.readline, b""):
                            if not raw:
                                break
                            line = raw.decode("utf-8", errors="replace").rstrip("\n")
                            try:
                                on_line(line)
                            except Exception:
                                pass
                except OSError:
                    pass

            threading.Thread(target=_bg_reader, daemon=True).start()

    return job


# ----- Singleton -----

_default_table: Optional[JobTable] = None


def get_default_job_table() -> JobTable:
    """Ленивая инициализация singleton."""
    global _default_table
    if _default_table is None:
        _default_table = JobTable()
    return _default_table


def reset_default_job_table() -> None:
    """Сброс (для тестов и recovery)."""
    global _default_table
    _default_table = None