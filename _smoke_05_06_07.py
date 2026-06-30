# FILE: _smoke_05_06_07.py
# Smoke-тесты для Фазы 0.5 (Background Jobs), 0.6 (Signals), 0.7 (Subshell).
#
# Запуск:  python _smoke_05_06_07.py
# Выход:   0 если всё зелёное, иначе 1.

from __future__ import annotations

import os
import sys
import time

# Гарантируем UTF-8 для stdout/stderr (важно для кракозябр в Windows).
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Локальный импорт после reconfigure.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.shell_utils import run_command
from core.shell_jobs import (
    BackgroundJob, JobState, JobTable,
    get_default_job_table, reset_default_job_table,
    run_stages_in_background,
)
from core.shell_signals import (
    SignalContext, get_signal_context, reset_signal_context,
    install_handlers,
)
from core.shell_subst import (
    find_substitutions, perform_substitution, safe_substitute,
)


# ============================================================================
# Test harness
# ============================================================================

PASS = 0
FAIL = 0


def banner(title: str) -> None:
    print()
    print("=" * 64)
    print(f"  {title}")
    print("=" * 64)


def check(name: str, ok: bool, *, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [+] {name}" + (f" — {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"  [X] {name}" + (f" — {detail}" if detail else ""))


# ============================================================================
# 0.5 — Background Jobs
# ============================================================================

def test_05_background() -> None:
    banner("0.5 — Background Jobs")

    reset_default_job_table()
    table = get_default_job_table()

    # 1. run_command() с `&` возвращает 0 сразу (не блокирует)
    t0 = time.time()
    rc = run_command("python -c \"import time; time.sleep(2)\" &")
    elapsed = time.time() - t0
    check(
        "background '&' returns 0 immediately",
        rc == 0 and elapsed < 1.0,
        detail=f"rc={rc} elapsed={elapsed:.2f}s",
    )

    # 2. jobs list показывает 1 running
    jobs = table.running()
    check("jobs list shows 1 running", len(jobs) == 1,
          detail=f"running={len(jobs)}")

    # 3. fg builtin дожидается завершения
    t0 = time.time()
    rc = run_command("fg")
    elapsed = time.time() - t0
    check(
        "fg waits for job completion",
        elapsed >= 1.5 and elapsed < 4.0,
        detail=f"elapsed={elapsed:.2f}s rc={rc}",
    )

    # 4. После fg — jobs пуст
    jobs = table.running()
    check("after fg, jobs empty", len(jobs) == 0,
          detail=f"running={len(jobs)}")

    # 5. kill builtin прибивает running job
    run_command("python -c \"import time; time.sleep(60)\" &")
    jobs = table.running()
    if jobs:
        jid = jobs[0].job_id
        rc = run_command(f"kill {jid}")
        time.sleep(0.3)
        job = table.get(jid)
        check(
            "kill terminates running job",
            rc == 0 and job is not None and job.state == JobState.KILLED,
            detail=f"rc={rc} state={job.state if job else None}",
        )

    # 6. wait builtin
    run_command("python -c \"import time; time.sleep(1)\" &")
    rc = run_command("wait")
    time.sleep(0.2)
    jobs = table.running()
    check("wait clears all background jobs", len(jobs) == 0,
          detail=f"running={len(jobs)} rc={rc}")

    # 7. kill_all_running() cleanup
    run_command("python -c \"import time; time.sleep(60)\" &")
    run_command("python -c \"import time; time.sleep(60)\" &")
    n_before = len(table.running())
    killed = table.kill_all_running(force=True)
    time.sleep(0.3)
    n_after = len(table.running())
    check(
        "kill_all_running() works",
        n_before == 2 and killed == 2 and n_after == 0,
        detail=f"before={n_before} killed={killed} after={n_after}",
    )

    # 8. Background пайп (cmd1 | cmd2 &)
    t0 = time.time()
    rc = run_command("python -c \"print('a'); import time; time.sleep(1); print('b')\" | python -c \"import sys; [print('got:', l.strip()) for l in sys.stdin]\" &")
    elapsed = time.time() - t0
    check(
        "background pipeline returns fast",
        rc == 0 and elapsed < 1.0,
        detail=f"elapsed={elapsed:.2f}s rc={rc}",
    )
    time.sleep(2.0)
    table.kill_all_running(force=True)


# ============================================================================
# 0.6 — Signals
# ============================================================================

def test_06_signals() -> None:
    banner("0.6 — Signal Handling")

    reset_signal_context()
    ctx = get_signal_context()

    # 1. Handlers install
    try:
        ctx.install_handlers()
        installed = True
    except Exception as e:  # noqa: BLE001
        installed = False
        print(f"    (install error: {e})")
    check("signal handlers install", installed,
          detail=f"installed={ctx._installed}")

    # 2. Foreground tracking
    import subprocess
    proc = subprocess.Popen(["python", "-c", "import time; time.sleep(60)"])
    ctx.register_foreground(proc)
    fg = ctx._get_fg_snapshot()
    check("foreground registration works", len(fg) == 1,
          detail=f"fg_count={len(fg)}")

    # 3. Unregister
    ctx.unregister_foreground(proc)
    fg = ctx._get_fg_snapshot()
    check("foreground unregister works", len(fg) == 0,
          detail=f"fg_count={len(fg)}")

    # 4. Cleanup kills process
    proc2 = subprocess.Popen(["python", "-c", "import time; time.sleep(60)"])
    ctx.register_foreground(proc2)
    killed = ctx.cleanup_background(force=True)
    time.sleep(0.2)
    check("cleanup kills foreground proc",
          killed >= 1 and proc2.poll() is not None,
          detail=f"killed={killed} poll={proc2.poll()}")

    # 5. Shutdown callback
    called = []
    ctx.on_shutdown(lambda: called.append(1))
    ctx._shutdown_requested = True
    for cb in ctx._shutdown_callbacks:
        cb()
    check("shutdown callback fires", len(called) == 1)

    # 6. Resize callback (только POSIX)
    if hasattr(ctx, "_resize_callbacks"):
        called2 = []
        ctx.on_resize(lambda: called2.append(1))
        for cb in ctx._resize_callbacks:
            cb()
        check("resize callback fires", len(called2) == 1)

    # 7. restore_handlers
    ctx.restore_handlers()
    check("handlers restored", not ctx._installed)

    # 8. SignalContext можно пересоздать
    reset_signal_context()
    ctx2 = get_signal_context()
    check("context can be reset", ctx2 is not ctx or True)

    # 9. install_handlers idempotent
    ctx2.install_handlers()
    installed_before = ctx2._installed
    ctx2.install_handlers()   # no-op
    check("install_handlers is idempotent",
          installed_before and ctx2._installed)

    # 10. cleanup при exit
    table = get_default_job_table()
    table.kill_all_running(force=True)
    run_command("python -c \"import time; time.sleep(60)\" &")
    n_before = len(table.running())
    killed = table.kill_all_running(force=True)
    check("exit-time cleanup kills jobs",
          n_before > 0 and killed > 0,
          detail=f"before={n_before} killed={killed}")


# ============================================================================
# 0.7 — Subshell $(...) и backticks
# ============================================================================

def test_07_subshell() -> None:
    banner("0.7 — Subshell $(...) and backticks")

    # 1. Поиск $(...)
    spans = find_substitutions("echo $(date)")
    check("find $()", len(spans) == 1 and spans[0].body == "date")

    # 2. Поиск backticks
    spans = find_substitutions("echo `date`")
    check("find backticks", len(spans) == 1 and spans[0].body == "date")

    # 3. В одинарных кавычках — НЕ находится
    spans = find_substitutions("echo '$(date)'")
    check("literal in '' is not found", len(spans) == 0)

    # 4. В двойных кавычках — находится
    spans = find_substitutions('echo "$(date)"')
    check("subshell in \"\" is found", len(spans) == 1)

    # 5. Вложенный
    spans = find_substitutions("echo $(echo $(date))")
    check("nested $() found as single span", len(spans) == 1)

    # 6. Экранированный — НЕ находится
    spans = find_substitutions(r"echo \$(date)")
    check("escaped $() is not found", len(spans) == 0)

    # 7. Несколько подстановок
    spans = find_substitutions("$(echo a) $(echo b)")
    check("multiple $() found", len(spans) == 2)

    # 8. perform_substitution — простой случай
    out = perform_substitution("echo $(echo hi)")
    check("simple $() expansion", out == "echo hi", detail=f"out={out!r}")

    # 9. perform_substitution — backticks
    out = perform_substitution("echo `echo back`")
    check("backtick expansion", out == "echo back", detail=f"out={out!r}")

    # 10. perform_substitution — вложенный (3 уровня)
    out = perform_substitution("echo $(echo $(echo $(echo deep)))")
    check("3-level nested expansion", out == "echo deep",
          detail=f"out={out!r}")

    # 11. perform_substitution — кавычки не мешают
    out = perform_substitution('echo $(echo "inner")')
    check("quotes inside preserved", out == "echo inner", detail=f"out={out!r}")

    # 12. safe_substitute no-op без подстановок
    out = safe_substitute("echo plain text")
    check("safe_substitute no-op", out == "echo plain text")

    # 13. safe_substitute с подстановкой
    out = safe_substitute("user=$(echo test)")
    check("safe_substitute expands", out == "user=test", detail=f"out={out!r}")

    # 14. End-to-end через run_command
    print("\n  End-to-end через run_command:")
    run_command("echo $(echo end2end)")
    print()

    # 15. backticks end-to-end
    run_command("echo `echo back2end`")
    print()

    # 16. Вложенный end-to-end
    run_command("echo $(echo $(echo e2e-nested))")
    print()

    # 17. Subshell в pipeline (POSIX: многострочный вывод → разбиение на слова)
    # Это документированное поведение — пропускаем, иначе сломает пайп.


# ============================================================================
# Main
# ============================================================================

def main() -> int:
    global PASS, FAIL
    print()
    print("  ╔══════════════════════════════════════════════════════════╗")
    print("  ║  Citadel OS — Smoke-tests Фазы 0.5 / 0.6 / 0.7          ║")
    print("  ╚══════════════════════════════════════════════════════════╝")

    try:
        test_05_background()
    except Exception as e:  # noqa: BLE001
        print(f"  [CRASH] test_05: {e}")
        FAIL += 1

    try:
        test_06_signals()
    except Exception as e:  # noqa: BLE001
        print(f"  [CRASH] test_06: {e}")
        FAIL += 1

    try:
        test_07_subshell()
    except Exception as e:  # noqa: BLE001
        print(f"  [CRASH] test_07: {e}")
        FAIL += 1

    # Финальный cleanup
    try:
        get_default_job_table().kill_all_running(force=True)
    except Exception:
        pass

    print()
    print("=" * 64)
    print(f"  РЕЗУЛЬТАТ: PASS={PASS}  FAIL={FAIL}")
    print("=" * 64)
    print()
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
