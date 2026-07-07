# FILE: main_handlers.py
# Citadel OS — реестр builtin-обработчиков для main.py.
#
# Фаза 2: вся кастомная логика команд Citadel (help/fetch/clear/center/pkg/
# netscan/ping/ip/sysmon/ps/kill/df/free/files/notes/crypto/passgen/launcher/
# recovery/history/weather/geo/log/alias/lock/ls/cd/cat) переехала из main.py
# сюда. Каждая команда — это handler-функция с сигнатурой
#   cmd_xxx(args: list[str]) -> int
# Handler'ы регистрируются в shell_utils._BUILTIN_HANDLERS через
# register_all(shell_utils) и далее вызываются из core.shell_utils.run_command().
#
# External-имя `kill` закреплено за cmd_kill (PID-процесс) — это
# намеренный override jkill-механизма из core.repl._register_default_builtins,
# см. строку "kill" в BUILTIN_HANDLERS ниже.
#
# exit/q/quit НЕ регистрируются — их обработку (return -1) делает
# core.repl._register_default_builtins().

from __future__ import annotations

import os
import sys
import subprocess
from typing import List, Optional

import config

# ----- core / system / apps imports ----------------------------------------
from core.interface import (
    clear_screen, terminal_print, display_fastfetch,
    display_help, display_table,
)
from core.auth import login_screen
from core.shell_history import get_default_history
from system.hardware import get_system_specs
from system.logger import log_command, log_security, tail_log
from system.process_mgr import get_process_list, kill_process, run_system_monitor
from system.network import scan_network, ping_host, display_interfaces
from system.package_mgr import run_package_manager
from system.recovery import run_recovery_menu
from system.geo import get_location, format_location
from system.user_config import get_aliases, add_alias, remove_alias
from apps.crypto import run_crypto_module
from apps.passgen import run_passgen
from apps.file_browser import run_file_browser
from apps.notes import run_notes_app
from apps.launcher import run_command_launcher
from apps.center import run_citadel_center
from apps.weather import run_weather_app


# ---------------------------------------------------------------------------
# Локальный legacy-список для команды `history` (старый формат:  idx  cmd).
# Синхронизируется из main.py (после run_command() — CMD_HISTORY.append).
# ---------------------------------------------------------------------------
CMD_HISTORY: List[str] = []


# ===========================================================================
# Вспомогательные функции (subprocess-вызовы, не-mock)
# ===========================================================================

def _run_linux_cmd(cmd_list: List[str]) -> str:
    """Безопасный запуск системных команд (Linux/macOS)."""
    try:
        result = subprocess.run(
            cmd_list, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return (f"{config.COLORS['RED']}Ошибка системы:{config.COLORS['RESET']}\n"
                f"{result.stderr.strip()}")
    except FileNotFoundError:
        return f"{config.COLORS['YELLOW']}[Системная утилита не найдена]{config.COLORS['RESET']}"
    except Exception as e:  # noqa: BLE001
        return str(e)


def _run_df() -> None:
    """Мониторинг свободного места на дисках (кроссплатформенный)."""
    theme_color = config.COLORS.get(
        getattr(config, 'THEME_COLOR', 'PURPLE'),
        config.COLORS["PURPLE"],
    )
    reset = config.COLORS["RESET"]

    print(f"\n{theme_color}--- Мониторинг дискового пространства ---{reset}")
    if os.name == 'nt':
        try:
            ps_cmd = (
                "powershell -command \"Get-Volume | Select-Object "
                "DriveLetter, FileSystemType, "
                "@{Name='SizeGB';Expression={[math]::round($_.Size/1GB,2)}}, "
                "@{Name='FreeGB';Expression={[math]::round($_.SizeRemaining/1GB,2)}} "
                "| Format-Table -HideTableHeaders\""
            )
            output = subprocess.check_output(ps_cmd, shell=True).decode('cp866').strip()

            headers = ["Диск", "ФС", "Размер", "Свободно"]
            rows: List[list] = []
            for line in output.split('\n'):
                parts = line.split()
                if len(parts) >= 3:
                    if len(parts) == 3:
                        rows.append(["N/A", parts[0], f"{parts[1]} GB", f"{parts[2]} GB"])
                    else:
                        rows.append([
                            f"{parts[0]}:", parts[1],
                            f"{parts[2]} GB", f"{parts[3]} GB",
                        ])
            display_table(headers, rows)
        except Exception as e:  # noqa: BLE001
            print(f"Ошибка PowerShell: {e}")
    else:
        print(_run_linux_cmd(['df', '-h']))
    print()


def _run_free() -> None:
    """Состояние оперативной памяти (кроссплатформенный)."""
    theme_color = config.COLORS.get(
        getattr(config, 'THEME_COLOR', 'PURPLE'),
        config.COLORS["PURPLE"],
    )
    reset = config.COLORS["RESET"]

    print(f"\n{theme_color}--- Мониторинг оперативной памяти ---{reset}")
    if os.name == 'nt':
        try:
            ps_cmd = (
                "powershell -command \"$os = Get-CimInstance Win32_OperatingSystem; "
                "$total = [math]::round($os.TotalVisibleMemorySize/1024/1024,2); "
                "$free = [math]::round($os.FreePhysicalMemory/1024/1024,2); "
                "\\\"$total|$free\\\"\""
            )
            output = subprocess.check_output(ps_cmd, shell=True).decode('cp866').strip()
            if "|" in output:
                total, free = output.split("|")
                headers = ["Параметр", "Объем памяти (GB)"]
                rows = [
                    ["Всего памяти", total],
                    ["Свободно памяти", free],
                    ["Использовано", str(round(float(total) - float(free), 2))],
                ]
                display_table(headers, rows)
        except Exception as e:  # noqa: BLE001
            print(f"Ошибка PowerShell: {e}")
    else:
        print(_run_linux_cmd(['free', '-h']))
    print()


# ===========================================================================
# Handler-функции (signature: cmd_xxx(args: list[str]) -> int)
# ===========================================================================

def cmd_help(args: List[str]) -> int:
    """help — таблица доступных команд (из core.interface)."""
    display_help()
    return 0


def cmd_fetch(args: List[str]) -> int:
    """fetch — перерисовать fastfetch-баннер."""
    clear_screen()
    display_fastfetch(get_system_specs())
    return 0


def cmd_clear(args: List[str]) -> int:
    """clear — очистить экран."""
    clear_screen()
    return 0


def cmd_center(args: List[str]) -> int:
    """center — главное меню Citadel Center."""
    run_citadel_center()
    return 0


def cmd_pkg(args: List[str]) -> int:
    """pkg — менеджер пакетов (install/remove/search/list/update)."""
    run_package_manager(args)
    return 0


def cmd_netscan(args: List[str]) -> int:
    """netscan — сканирование локальной сети."""
    scan_network()
    return 0


def cmd_ping(args: List[str]) -> int:
    """ping — интерактивный ping хоста."""
    ping_host()
    return 0


def cmd_ip(args: List[str]) -> int:
    """ip — сетевые интерфейсы."""
    display_interfaces()
    return 0


def cmd_sysmon(args: List[str]) -> int:
    """sysmon — системный монитор (CPU/RAM/Network)."""
    run_system_monitor()
    return 0


def cmd_ps(args: List[str]) -> int:
    """ps — таблица процессов."""
    headers, rows = get_process_list()
    display_table(headers, rows)
    print()
    return 0


def cmd_kill(args: List[str]) -> int:
    """
    kill <PID> — завершить процесс по PID.

    External-имя `kill` перехватывается здесь ДО fallback'а в shell_utils.py
    (строки 376-383) и ДО jkill-маршрутизации. Регистрация в BUILTIN_HANDLERS
    происходит первой — см. register_all().
    """
    red = config.COLORS["RED"]
    green = config.COLORS["GREEN"]
    reset = config.COLORS["RESET"]

    if not args:
        print("Укажите PID процесса.\n")
        return 2
    success, msg = kill_process(args[0])
    if success:
        print(f"{green}[ SUCCESS ]: {msg}{reset}\n")
        return 0
    print(f"{red}[ ERROR ]: {msg}{reset}\n")
    return 1


def cmd_df(args: List[str]) -> int:
    """df — свободное место на дисках."""
    _run_df()
    return 0


def cmd_free(args: List[str]) -> int:
    """free — состояние оперативной памяти."""
    _run_free()
    return 0


def cmd_files(args: List[str]) -> int:
    """files — файловый менеджер."""
    run_file_browser()
    return 0


def cmd_notes(args: List[str]) -> int:
    """notes — приложение заметок."""
    run_notes_app()
    return 0


def cmd_crypto(args: List[str]) -> int:
    """crypto — модуль шифрования."""
    run_crypto_module()
    return 0


def cmd_passgen(args: List[str]) -> int:
    """passgen — генератор паролей."""
    run_passgen()
    return 0


def cmd_launcher(args: List[str]) -> int:
    """launcher — запуск внешних команд/приложений."""
    run_command_launcher()
    return 0


def cmd_recovery(args: List[str]) -> int:
    """recovery — меню восстановления системы."""
    run_recovery_menu()
    return 0


def cmd_history(args: List[str]) -> int:
    """
    history — сессионный список (legacy-формат: idx  cmd).

    Источник: CMD_HISTORY, наполняется из main.py. Встроенный `history`
    в shell_utils (HistoryManager-формат с timestamp/exit_code) НЕ
    используется — наш handler перехватывает раньше через _try_builtin().
    """
    print("\n=== ИСТОРИЯ КОМАНД СЕССИИ ===")
    for idx, h_cmd in enumerate(CMD_HISTORY, 1):
        print(f"  {idx:<4} {h_cmd}")
    print()
    return 0


def cmd_weather(args: List[str]) -> int:
    """weather — прогноз погоды (по последней известной локации)."""
    run_weather_app()
    return 0


def cmd_geo(args: List[str]) -> int:
    """geo [refresh] — определение местоположения по IP."""
    print(f"{config.COLORS['CYAN']}[ INFO ]: Определяю местоположение...{config.COLORS['RESET']}")
    loc = get_location(force_refresh="refresh" in args)
    if not loc:
        print(f"{config.COLORS['RED']}[ ERROR ]: Не удалось определить локацию. "
              f"Проверьте интернет.{config.COLORS['RESET']}")
        return 1
    print()
    print(format_location(loc))
    print()
    return 0


def cmd_log(args: List[str]) -> int:
    """log [N] — последние N строк журнала безопасности (по умолчанию 20)."""
    try:
        n = int(args[0]) if args else 20
    except ValueError:
        n = 20
    lines = tail_log(n)
    if not lines:
        print("(лог пуст или недоступен)")
        return 0
    print(f"\n=== ПОСЛЕДНИЕ {len(lines)} ЗАПИСЕЙ ЖУРНАЛА ===")
    for ln in lines:
        print(ln)
    print()
    return 0


def cmd_alias(args: List[str]) -> int:
    """
    alias [list | add NAME BODY | remove NAME] — управление алиасами.

    В shell_utils._builtin_alias уже есть похожий handler, но мы
    переопределяем ради legacy-формата вывода (system.user_config API
    и русскоязычные подсказки).
    """
    if not args or args[0] in ("list", "-l"):
        aliases = get_aliases()
        if not aliases:
            print("Алиасов пока нет. Добавьте: alias add <имя> <команда>")
            return 0
        print("\n=== АЛИАСЫ КОМАНД ===")
        for name, body in sorted(aliases.items()):
            print(f"  {name:<12} → {body}")
        print()
        return 0

    if args[0] == "add" and len(args) >= 3:
        name, body = args[1], " ".join(args[2:])
        if add_alias(name, body):
            print(f"[ OK ] Алиас '{name}' → '{body}' добавлен.")
            return 0
        print("[ ERROR ] Не удалось сохранить алиас.")
        return 1

    if args[0] in ("remove", "rm", "del") and len(args) >= 2:
        if remove_alias(args[1]):
            print(f"[ OK ] Алиас '{args[1]}' удалён.")
            return 0
        print(f"[ INFO ] Алиас '{args[1]}' не найден.")
        return 1

    print("Использование:")
    print("  alias list                    — список всех алиасов")
    print("  alias add <имя> <команда>     — добавить/обновить алиас")
    print("  alias remove <имя>            — удалить алиас")
    return 2


def cmd_lock(args: List[str]) -> int:
    """lock — повторная аутентификация (не выходя из сессии)."""
    yellow = config.COLORS["YELLOW"]
    green = config.COLORS["GREEN"]
    reset = config.COLORS["RESET"]

    print(f"{yellow}[ LOCK ]: Запрошена повторная аутентификация...{reset}")
    log_security("Screen lock requested by user")
    login_screen()
    print(f"{green}[ OK ]: Сессия разблокирована.{reset}")
    return 0


def cmd_ls(args: List[str]) -> int:
    """ls — список файлов в текущей директории (с цветовой маркировкой)."""
    blue = config.COLORS["BLUE"]
    reset = config.COLORS["RESET"]
    try:
        items = sorted(os.listdir('.'))
        for item in items:
            full_path = os.path.join('.', item)
            if os.path.isdir(full_path):
                print(f"{blue}[DIR]  {item}{reset}")
            else:
                print(f"       {item}")
        print()
    except Exception as e:  # noqa: BLE001
        print(f"Ошибка: {e}\n")
        return 1
    return 0


def cmd_cat(args: List[str]) -> int:
    """cat <file> — вывести содержимое текстового файла."""
    if not args:
        print("Укажите файл.\n")
        return 2
    try:
        with open(args[0], "r", encoding="utf-8", errors="ignore") as f:
            print(f"\n--- {args[0]} ---\n{f.read()}\n----------------\n")
    except Exception as e:  # noqa: BLE001
        print(f"Ошибка: {e}\n")
        return 1
    return 0


def cmd_cd(args: List[str]) -> int:
    """
    cd [path] — сменить рабочую директорию.

    ВАЖНО: _try_builtin() в core.shell_utils.run_command() срабатывает РАНЬШЕ,
    чем hardcoded-ветка `if argv[0] == "cd":` (run_command:322). Поэтому,
    если `cd` зарегистрирован как builtin (мы так делаем), наш handler
    затеняет встроенный и должен сам повторить его логику: раскрыть `~`,
    обновить VariableStore.PWD, корректно обработать ошибки.
    """
    target = args[0] if args else os.path.expanduser("~")
    if target == "~" or target.startswith("~/"):
        target = os.path.expanduser(target)
    try:
        from core.shell_state import get_default_store
        store = get_default_store()
        expanded = store.expand(target)
        os.chdir(expanded)
        store.refresh_pwd(os.getcwd())
    except FileNotFoundError:
        print(f"cd: нет такой директории: {target}\n")
        return 1
    except OSError as e:
        print(f"cd: {e}\n")
        return 1
    return 0


# ===========================================================================
# Реестр handler'ов
# ===========================================================================

BUILTIN_HANDLERS = {
    # Базовые Citadel-команды (help/clear/fetch — перезаписываем
    # облегчённые версии из core.repl._register_default_builtins).
    "help":    cmd_help,
    "fetch":   cmd_fetch,
    "clear":   cmd_clear,
    # Системные
    "center":  cmd_center,
    "pkg":     cmd_pkg,
    "netscan": cmd_netscan,
    "ping":    cmd_ping,
    "ip":      cmd_ip,
    "sysmon":  cmd_sysmon,
    "ps":      cmd_ps,
    "kill":    cmd_kill,        # ← override: PID, не jkill
    "df":      cmd_df,
    "free":    cmd_free,
    "files":   cmd_files,
    "notes":   cmd_notes,
    "crypto":  cmd_crypto,
    "passgen": cmd_passgen,
    "launcher": cmd_launcher,
    "recovery": cmd_recovery,
    "history": cmd_history,     # ← override: legacy-формат
    "weather": cmd_weather,
    "geo":     cmd_geo,
    "log":     cmd_log,
    "alias":   cmd_alias,       # ← override: legacy-формат
    "lock":    cmd_lock,
    "ls":      cmd_ls,
    "cd":      cmd_cd,          # ← no-op: реальный cd в run_command()
    "cat":     cmd_cat,
    # exit/q/quit НЕ регистрируем — их держит core.repl (sentinel -1).
}


def register_all(shell_utils_module) -> None:
    """
    Зарегистрировать все handler'ы из BUILTIN_HANDLERS в shell_utils.

    Идемпотентно: повторный вызов просто перезатирает записи (это и есть
    наше намерение — перебиваем help/clear/fetch из _register_default_builtins).
    """
    for name, handler in BUILTIN_HANDLERS.items():
        shell_utils_module.register_builtin(name, handler)
