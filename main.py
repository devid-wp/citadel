"""
Citadel Shell — main entry point (v3.0, Фаза 2).

Структура:
  1. login_screen()                  — pre-REPL аутентификация.
  2. EnvAwarenessModule              — адаптивная тема (HUD).
  3. install_completer()             — Tab-дополнение.
  4. main_handlers.register_all()    — кастомные builtin'ы.
  5. core.repl._register_default_builtins() — help/clear/exit/q/quit/fetch/jkill.
  6. REPL-цикл:
        while True:
            user_input = input(prompt)
            rc = run_command(user_input)   # ← единая точка входа
            if rc == -1: break             # ← sentinel от exit/q/quit
  7. atexit + sys.excepthook          — снапшот в ~/.citadel_recovery/ при крахе.

Вся кастомная логика команд (help, fetch, clear, center, pkg, ...) переехала
в main_handlers.py — здесь только bootstrap и цикл.
"""
from __future__ import annotations
from core.executor import run_command

import atexit
import os
import sys
import traceback

import config

from core.interface import clear_screen, terminal_print, display_fastfetch
from core.auth import login_screen
from core.shell_utils import install_completer
from core.repl import _register_default_builtins, HistoryBridge
from system.hardware import get_system_specs
from system.logger import log_command, log_security
from system.geo import get_location
from system.recovery import (
    install_recovery_hooks,
    snapshot_session,
    REASON_EXIT,
)

# AR-HUD subsystem.
from core.theme_state import get_theme_state
from core.interface import get_registry
from modules.env_awareness_module import EnvAwarenessModule

# Кастомные builtin'ы Citadel. Регистрируются ПОСЛЕ дефолтных, чтобы
# перезатереть help/clear/fetch расширенными версиями из main_handlers.
import core.shell_utils as _shell_utils
from main_handlers import register_all as _register_main_handlers, CMD_HISTORY


def main() -> None:
    # 1. Авторизация
    login_screen()
    log_security("User logged in successfully")

    # 2. EnvAwarenessModule — daemon-поток, обновляет тему по времени суток.
    #    Делаем ДО display_fastfetch(), чтобы первая отрисовка учитывала
    #    актуальную палитру. stop_all() вызывается в финализаторе.
    registry = get_registry()
    env_module = EnvAwarenessModule()
    registry.register(env_module)
    registry.start_all()
    log_security(
        f"EnvAwarenessModule started, current theme: "
        f"{get_theme_state().current_theme.value}"
    )

    # 3. Tab-дополнение
    install_completer()

    # 4. Регистрация builtin'ов.
    #    4a) core/repl._register_default_builtins() — help/clear/exit/q/quit/fetch/jkill.
    #    4b) main_handlers.register_all()           — расширенные Citadel-команды
    #        (перезатирает help/clear/fetch; exit/q/quit не трогает).
    _register_default_builtins()
    _register_main_handlers(_shell_utils)

    # 4c. HistoryBridge — readline <-> HistoryManager.
    #     Нам нужен, чтобы:
    #       • ↑/↓ работали в интерактивной сессии (readline-буфер);
    #       • ~/.citadel_history персистился через HistoryManager.finish() →
    #         JSONL append (см. core/shell_history.py:_append_to_disk);
    #       • на exit/Ctrl-D/EofError — bridge.close() делает fsync +
    #         write_history_file для readline-буфера.
    bridge = HistoryBridge()
    bridge.setup_readline()

    # 4d. Recovery-хуки (Фаза 2.5):
    #       • atexit — снапшот при ЛЮБОМ нормальном выходе (exit / return /
    #         Ctrl-D / необработанное исключение, не пойманное try/except);
    #       • sys.excepthook — снапшот при непойманном исключении в основном
    #         потоке (типичный crash REPL'а).
    # install_recovery_hooks() возвращает setter для cwd/истории, чтобы
    # обновлять их по ходу сессии.
    set_session_state = install_recovery_hooks(
        initial_cwd=os.getcwd(),
        recent_cmds=[],
    )
    # Гарантируем снапшот и при штатном выходе (exit/q/quit) — дополнительно
    # к excepthook. atexit НЕ срабатывает на SIGKILL/SIGTERM, но срабатывает
    # на sys.exit(), KeyboardInterrupt после основного try, и нормальном return.
    atexit.register(
        snapshot_session,
        reason=REASON_EXIT,
        cwd=os.getcwd(),
        recent_cmds_provider=lambda: list(CMD_HISTORY)[-20:],
    )

    # 5. Баннер и fastfetch
    specs = get_system_specs()
    clear_screen()
    display_fastfetch(specs)

    theme_color = config.COLORS.get(
        getattr(config, 'THEME_COLOR', 'PURPLE'),
        config.COLORS["PURPLE"],
    )
    reset = config.COLORS["RESET"]
    cyan = config.COLORS["CYAN"]
    purple = config.COLORS["PURPLE"]
    red = config.COLORS["RED"]
    yellow = config.COLORS["YELLOW"]

    print(f"Citadel Shell v{config.VERSION} успешно запущена поверх "
          f"{sys.platform.capitalize()} Kernel.")
    print(f"Введите {cyan}'help'{reset} для вывода списка расширенных утилит.")
    print(f"Используйте {cyan}Tab{reset} для автодополнения команд и "
          f"стрелки {cyan}↑/↓{reset} для истории.\n")

    # Приветствие с геолокацией (best-effort, без падения при отсутствии сети).
    try:
        loc = get_location()
        if loc:
            print(f"{yellow}[ GEO ]{reset}: {loc.get('city', '—')}, "
                  f"{loc.get('country', '—')} ({loc.get('ip', '—')})  "
                  f"→ введите {cyan}'weather'{reset} для прогноза.\n")
    except Exception:  # noqa: BLE001
        pass

    # 6. REPL-цикл. Вся диспетчеризация команд — в run_command().
    while True:
        current_dir = os.getcwd()
        user_name = getattr(config, 'USER_NAME', 'User')
        prompt = f"{purple}[Citadel@{user_name} {os.path.basename(current_dir)}]$ {reset}"

        try:
            user_input = input(prompt).strip()
        except KeyboardInterrupt:
            print("\nИспользуйте 'exit' или 'q' для выхода.")
            continue
        except EOFError:
            # Ctrl-D / конец pipe. Завершаем штатно: bridge.close() сохранит
            # историю, atexit-хук сделает снапшот сессии.
            print()
            break

        if not user_input:
            continue

        # Аудит: пишем в журнал + legacy-список для cmd_history.
        log_command(user_input)
        CMD_HISTORY.append(user_input)
        set_session_state(
            cwd=os.getcwd(),
            recent_cmds=list(CMD_HISTORY)[-20:],
        )

        # HistoryBridge: каждая команда оборачивается в begin/finish.
        # finish() пишет JSONL-строку в ~/.citadel_history сразу после
        # завершения команды (см. core/shell_history.py:_append_to_disk).
        # Это значит, что история НЕ теряется даже при kill -9 в середине
        # сессии — последняя записанная команда уже на диске.
        handle = bridge.history.begin(user_input)
        try:
            rc = run_command(user_input)
        except Exception as e:  # noqa: BLE001
            print(f"{config.COLORS['RED']}Ошибка выполнения:{config.COLORS['RESET']} {e}\n")
            rc = 1
        finally:
            bridge.history.finish(handle, exit_code=rc)
        bridge.add_readline(user_input)

        # Sentinel -1: выход (выставлен exit/q/quit через core/repl._register_default_builtins).
        if rc == -1:
            log_security("User exited Citadel Shell")
            clear_screen()
            terminal_print(
                "Выгрузка Citadel Shell. Отключение терминала...",
                color_code=config.COLORS["RED"],
            )
            break

    # 7. Graceful shutdown. Сохраняем readline-буфер в файл и делаем
    #    fsync на JSONL-историю (на случай kill -9 сразу после return).
    try:
        bridge.close()
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # Ctrl-C в самом начале (до login / до REPL) — корректный выход
        # с recovery-снапшотом.
        print("\n[ EXIT ]: Принудительное завершение.")
        try:
            snapshot_session(
                reason=REASON_INTERRUPT,
                cwd=os.getcwd(),
                recent_cmds_provider=lambda: list(CMD_HISTORY)[-20:],
            )
        except Exception:  # noqa: BLE001
            pass
    except SystemExit:
        # sys.exit() из login_screen при провале auth. Пробрасываем дальше,
        # но atexit всё равно отработает.
        raise
    except Exception as e:  # noqa: BLE001
        # Необработанное исключение в main(). sys.excepthook его уже
        # залогировал и сделал снапшот; тут просто печатаем traceback
        # в stderr для пользователя (если excepthook ещё не отработал —
        # например, в тестах без перехвата).
        traceback.print_exc()
        try:
            snapshot_session(
                reason=REASON_CRASH,
                cwd=os.getcwd(),
                recent_cmds_provider=lambda: list(CMD_HISTORY)[-20:],
            )
        except Exception:  # noqa: BLE001
            pass
    finally:
        # Корректная остановка HUD-модулей. На случай, если процесс
        # прерывается до завершения main() (Ctrl-C в начале сессии) —
        # get_registry() всё равно вернёт singleton с зарегистрированными
        # модулями.
        try:
            get_registry().stop_all()
        except Exception:  # noqa: BLE001
            pass
