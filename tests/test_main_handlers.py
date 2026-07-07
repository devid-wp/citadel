"""
Tests for main_handlers.py (Citadel OS, Фаза 2).

Покрывает:
  1. test_all_handlers_registered        — все имена из BUILTIN_HANDLERS
                                           попадают в shell_utils._BUILTIN_HANDLERS.
  2. test_register_all_idempotent        — повторный register_all() не падает.
  3. test_exit_returns_sentinel          — exit/q/quit/EXIT → rc == -1.
  4. test_kill_routes_to_main_handler    — kill <PID> идёт в main_handlers.cmd_kill,
                                           а не в shell_utils._builtin_kill (job).
  5. test_jkill_routes_to_job_control    — jkill <job_id> идёт в _builtin_kill.
  6. test_pure_handlers_return_int       — параметризованный: help/fetch/clear/ls/
                                           history/env/vars/type → int.
  7. test_cd_returns_zero                — cd ~ → 0.
  8. test_unknown_command                — xyz_unknown → rc != 0.

Все handler'ы здесь исполняются через core.shell_utils.run_command() —
ту же точку входа, что и main.py.
"""
from __future__ import annotations

import pytest

# Регистрируем default'ы (help/clear/exit/q/quit/fetch/jkill) и main_handlers
# один раз на сессию. autouse-фикстура conftest'а чистит синглтоны
# (history, store, jobs, signals) между тестами, но _BUILTIN_HANDLERS
# очищать не нужно — register_all() идемпотентен.
from core.repl import _register_default_builtins
import core.shell_utils as _shell
import main_handlers


# ---------------------------------------------------------------------------
# Фикстура: поднимает builtin'ы один раз на тест-сессию.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module", autouse=True)
def _bootstrap_builtins():
    _register_default_builtins()
    main_handlers.register_all(_shell)


# ============================================================================
# 1. Все имена из BUILTIN_HANDLERS зарегистрированы в shell_utils
# ============================================================================

def test_all_handlers_registered():
    """Каждое имя в BUILTIN_HANDLERS должно попасть в shell_utils._BUILTIN_HANDLERS."""
    for name in main_handlers.BUILTIN_HANDLERS:
        assert name in _shell._BUILTIN_HANDLERS, (
            f"handler '{name}' не зарегистрирован в shell_utils"
        )
    # exit/q/quit НЕ регистрируем — оставляем core/repl.
    for sentinel in ("exit", "q", "quit"):
        assert sentinel not in main_handlers.BUILTIN_HANDLERS


# ============================================================================
# 2. register_all() идемпотентен
# ============================================================================

def test_register_all_idempotent():
    """Повторный register_all() не падает и сохраняет те же handler'ы."""
    before = dict(_shell._BUILTIN_HANDLERS)
    main_handlers.register_all(_shell)
    main_handlers.register_all(_shell)
    after = dict(_shell._BUILTIN_HANDLERS)
    for name in main_handlers.BUILTIN_HANDLERS:
        assert before[name] is after[name], f"handler '{name}' сменился после re-register"


# ============================================================================
# 3. exit / q / quit → sentinel -1
# ============================================================================

@pytest.mark.parametrize("cmd", ["exit", "q", "quit", "EXIT", "Q", "Quit"])
def test_exit_returns_sentinel(cmd):
    """Любая форма exit/q/quit возвращает -1 через core/repl._builtin_exit."""
    assert _shell.run_command(cmd) == -1


# ============================================================================
# 4. kill → main_handlers.cmd_kill (а НЕ job-control)
# ============================================================================

def test_kill_routes_to_main_handler(monkeypatch):
    """kill <PID> должен попасть в main_handlers.cmd_kill, не в _builtin_kill."""
    called = {"kill_proc": None, "job_kill": None}

    def fake_kill_process(pid):
        called["kill_proc"] = pid
        return True, "killed"

    def fake_builtin_kill(args):
        called["job_kill"] = args
        return 0

    monkeypatch.setattr(main_handlers, "kill_process", fake_kill_process)
    # Прячем оригинальный _builtin_kill, чтобы убедиться, что его не зовут.
    monkeypatch.setattr(_shell, "_builtin_kill", fake_builtin_kill)

    rc = _shell.run_command("kill 9999")
    assert called["kill_proc"] == "9999", "kill_process не был вызван"
    assert called["job_kill"] is None, "job-control _builtin_kill не должен сработать"
    assert rc == 0


# ============================================================================
# 5. jkill → job-control _builtin_kill
# ============================================================================

def test_jkill_routes_to_job_control(monkeypatch):
    """jkill <job_id> идёт в shell_utils._builtin_kill, не в main_handlers.cmd_kill."""
    called = {"job_kill": None, "kill_proc": None}

    def fake_job_kill(args):
        called["job_kill"] = args
        return 1   # job not found

    def fake_kill_process(pid):
        called["kill_proc"] = pid
        return True, "killed"

    # Подменяем handler в реестре — _try_builtin зовёт именно его,
    # а не ссылку из register_builtin (та указывает на оригинал).
    monkeypatch.setitem(_shell._BUILTIN_HANDLERS, "jkill", fake_job_kill)
    monkeypatch.setattr(main_handlers, "kill_process", fake_kill_process)

    rc = _shell.run_command("jkill 1")
    assert called["job_kill"] == ["1"], "_builtin_kill не вызван"
    assert called["kill_proc"] is None, "main_handlers.cmd_kill не должен сработать"
    assert rc == 1   # job not found


# ============================================================================
# 6. Чистые handler'ы возвращают int
# ============================================================================

@pytest.mark.parametrize(
    "cmd,args_check",
    [
        ("help", None),
        ("fetch", None),
        ("clear", None),
        ("ls", None),
        ("history", None),
        ("env", None),   # встроенный в run_command
        ("vars", None),  # встроенный в run_command
        ("type", ["echo"]),
    ],
)
def test_pure_handlers_return_int(cmd, args_check):
    """Каждый из перечисленных handler'ов возвращает int (0 или !=0)."""
    line = cmd if args_check is None else f"{cmd} {' '.join(args_check)}"
    rc = _shell.run_command(line)
    assert isinstance(rc, int), f"{line} вернул {type(rc).__name__}, не int"


# ============================================================================
# 7. cd возвращает 0
# ============================================================================

def test_cd_returns_zero(tmp_path, monkeypatch):
    """cd <existing dir> → 0.

    Зовём cmd_cd напрямую (не через run_command) и оборачиваем в
    monkeypatch.chdir, чтобы не загрязнять cwd процесса для других тестов
    (test_shell_state::test_builtin_pwd чувствителен к os.getcwd()).
    """
    monkeypatch.chdir(tmp_path)
    rc = main_handlers.cmd_cd(["."])
    assert rc == 0


# ============================================================================
# 8. Неизвестная команда → rc != 0
# ============================================================================

def test_unknown_command():
    """xyz_unknown — не builtin и не в PATH → rc != 0 (FileNotFoundError → 127)."""
    rc = _shell.run_command("xyz_unknown_xyz_12345")
    assert rc != 0
