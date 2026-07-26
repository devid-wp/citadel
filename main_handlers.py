# FILE: main_handlers.py
# Citadel OS — registry of builtin handlers for main.py.
#
# Phase 2: all custom Citadel command logic (help/fetch/clear/center/pkg/
# netscan/ping/ip/sysmon/ps/kill/df/free/files/notes/crypto/passgen/launcher/
# recovery/history/weather/geo/log/alias/lock/ls/cd/cat) has moved out of
# main.py into here. Each command is a handler function with the signature
#   cmd_xxx(args: list[str]) -> int
# Handlers are registered in shell_utils._BUILTIN_HANDLERS via
# register_all(shell_utils) and then called from core.shell_utils.run_command().
#
# The external name `kill` is bound to cmd_kill (process PID) — this is
# an intentional override of the jkill mechanism from
# core.repl._register_default_builtins, see the "kill" entry in
# BUILTIN_HANDLERS below.
#
# exit/q/quit are NOT registered — core.repl._register_default_builtins()
# handles them (returning -1).

from __future__ import annotations
from core.shell_arith import eval_test_condition

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
# Local legacy list for the `history` command (legacy format: idx  cmd).
# Synchronized from main.py (after run_command() — CMD_HISTORY.append).
# ---------------------------------------------------------------------------
CMD_HISTORY: List[str] = []


# ===========================================================================
# Helper functions (subprocess calls, non-mock)
# ===========================================================================

def _run_linux_cmd(cmd_list: List[str]) -> str:
    """Safe execution of system commands (Linux/macOS)."""
    try:
        result = subprocess.run(
            cmd_list, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return (f"{config.COLORS['RED']}System error:{config.COLORS['RESET']}\n"
                f"{result.stderr.strip()}")
    except FileNotFoundError:
        return f"{config.COLORS['YELLOW']}[System utility not found]{config.COLORS['RESET']}"
    except Exception as e:  # noqa: BLE001
        return str(e)


def _run_df() -> None:
    """Free disk space monitor (cross-platform)."""
    theme_color = config.COLORS.get(
        getattr(config, 'THEME_COLOR', 'PURPLE'),
        config.COLORS["PURPLE"],
    )
    reset = config.COLORS["RESET"]

    print(f"\n{theme_color}--- Disk Space Monitor ---{reset}")
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

            headers = ["Disk", "FS", "Size", "Free"]
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
            print(f"PowerShell error: {e}")
    else:
        print(_run_linux_cmd(['df', '-h']))
    print()


def _run_free() -> None:
    """RAM status (cross-platform)."""
    theme_color = config.COLORS.get(
        getattr(config, 'THEME_COLOR', 'PURPLE'),
        config.COLORS["PURPLE"],
    )
    reset = config.COLORS["RESET"]

    print(f"\n{theme_color}--- RAM Monitor ---{reset}")
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
                headers = ["Metric", "Memory (GB)"]
                rows = [
                    ["Total memory", total],
                    ["Free memory", free],
                    ["Used", str(round(float(total) - float(free), 2))],
                ]
                display_table(headers, rows)
        except Exception as e:  # noqa: BLE001
            print(f"PowerShell error: {e}")
    else:
        print(_run_linux_cmd(['free', '-h']))
    print()


# ===========================================================================
# Handler functions (signature: cmd_xxx(args: list[str]) -> int)
# ===========================================================================

def cmd_help(args: List[str]) -> int:
    """help — table of available commands (from core.interface)."""
    display_help()
    return 0


def cmd_fetch(args: List[str]) -> int:
    """fetch — redraw the fastfetch banner."""
    clear_screen()
    display_fastfetch(get_system_specs())
    return 0


def cmd_clear(args: List[str]) -> int:
    """clear — clear the screen."""
    clear_screen()
    return 0


def cmd_center(args: List[str]) -> int:
    """center — main Citadel Center menu."""
    run_citadel_center()
    return 0


def cmd_pkg(args: List[str]) -> int:
    """pkg — package manager (install/remove/search/list/update)."""
    run_package_manager(args)
    return 0


def cmd_netscan(args: List[str]) -> int:
    """netscan — scan the local network."""
    scan_network()
    return 0


def cmd_ping(args: List[str]) -> int:
    """ping — interactive host ping."""
    ping_host()
    return 0


def cmd_ip(args: List[str]) -> int:
    """ip — network interfaces."""
    display_interfaces()
    return 0


def cmd_sysmon(args: List[str]) -> int:
    """sysmon — system monitor (CPU/RAM/Network)."""
    run_system_monitor()
    return 0


def cmd_ps(args: List[str]) -> int:
    """ps — process table."""
    headers, rows = get_process_list()
    display_table(headers, rows)
    print()
    return 0


def cmd_kill(args: List[str]) -> int:
    """
    kill <PID> — terminate a process by PID.

    The external name `kill` is intercepted here BEFORE the fallback in
    shell_utils.py (lines 376-383) and BEFORE jkill routing. It is
    registered first in BUILTIN_HANDLERS — see register_all().
    """
    red = config.COLORS["RED"]
    green = config.COLORS["GREEN"]
    reset = config.COLORS["RESET"]

    if not args:
        print("Specify a process PID.\n")
        return 2
    success, msg = kill_process(args[0])
    if success:
        print(f"{green}[ SUCCESS ]: {msg}{reset}\n")
        return 0
    print(f"{red}[ ERROR ]: {msg}{reset}\n")
    return 1


def cmd_df(args: List[str]) -> int:
    """df — free disk space."""
    _run_df()
    return 0


def cmd_free(args: List[str]) -> int:
    """free — RAM status."""
    _run_free()
    return 0


def cmd_files(args: List[str]) -> int:
    """files — file manager."""
    run_file_browser()
    return 0


def cmd_notes(args: List[str]) -> int:
    """notes — notes application."""
    run_notes_app()
    return 0


def cmd_crypto(args: List[str]) -> int:
    """crypto — encryption module."""
    run_crypto_module()
    return 0


def cmd_passgen(args: List[str]) -> int:
    """passgen — password generator."""
    run_passgen()
    return 0


def cmd_launcher(args: List[str]) -> int:
    """launcher — run external commands/applications."""
    run_command_launcher()
    return 0


def cmd_recovery(args: List[str]) -> int:
    """recovery — system recovery menu."""
    run_recovery_menu()
    return 0


def cmd_history(args: List[str]) -> int:
    """
    history — session list (legacy format: idx  cmd).

    Source: CMD_HISTORY, populated from main.py. The built-in `history`
    in shell_utils (HistoryManager format with timestamp/exit_code) is
    NOT used — our handler intercepts earlier via _try_builtin().
    """
    print("\n=== SESSION COMMAND HISTORY ===")
    for idx, h_cmd in enumerate(CMD_HISTORY, 1):
        print(f"  {idx:<4} {h_cmd}")
    print()
    return 0


def cmd_weather(args: List[str]) -> int:
    """weather — weather forecast (based on the last known location)."""
    run_weather_app()
    return 0


def cmd_geo(args: List[str]) -> int:
    """geo [refresh] — determine location by IP."""
    print(f"{config.COLORS['CYAN']}[ INFO ]: Detecting location...{config.COLORS['RESET']}")
    loc = get_location(force_refresh="refresh" in args)
    if not loc:
        print(f"{config.COLORS['RED']}[ ERROR ]: Could not determine location. "
              f"Check your internet connection.{config.COLORS['RESET']}")
        return 1
    print()
    print(format_location(loc))
    print()
    return 0


def cmd_log(args: List[str]) -> int:
    """log [N] — last N lines of the security log (default 20)."""
    try:
        n = int(args[0]) if args else 20
    except ValueError:
        n = 20
    lines = tail_log(n)
    if not lines:
        print("(log is empty or unavailable)")
        return 0
    print(f"\n=== LAST {len(lines)} LOG ENTRIES ===")
    for ln in lines:
        print(ln)
    print()
    return 0


def cmd_alias(args: List[str]) -> int:
    """
    alias [list | add NAME BODY | remove NAME] — manage aliases.

    shell_utils._builtin_alias already has a similar handler, but we
    override it to keep the legacy output format (system.user_config API
    and localized hints).
    """
    if not args or args[0] in ("list", "-l"):
        aliases = get_aliases()
        if not aliases:
            print("No aliases yet. Add one: alias add <name> <command>")
            return 0
        print("\n=== COMMAND ALIASES ===")
        for name, body in sorted(aliases.items()):
            print(f"  {name:<12} → {body}")
        print()
        return 0

    if args[0] == "add" and len(args) >= 3:
        name, body = args[1], " ".join(args[2:])
        if add_alias(name, body):
            print(f"[ OK ] Alias '{name}' → '{body}' added.")
            return 0
        print("[ ERROR ] Could not save alias.")
        return 1

    if args[0] in ("remove", "rm", "del") and len(args) >= 2:
        if remove_alias(args[1]):
            print(f"[ OK ] Alias '{args[1]}' removed.")
            return 0
        print(f"[ INFO ] Alias '{args[1]}' not found.")
        return 1

    print("Usage:")
    print("  alias list                    — list all aliases")
    print("  alias add <name> <command>    — add/update an alias")
    print("  alias remove <name>           — remove an alias")
    return 2


def cmd_lock(args: List[str]) -> int:
    """lock — re-authenticate without leaving the session."""
    yellow = config.COLORS["YELLOW"]
    green = config.COLORS["GREEN"]
    reset = config.COLORS["RESET"]

    print(f"{yellow}[ LOCK ]: Re-authentication requested...{reset}")
    log_security("Screen lock requested by user")
    login_screen()
    print(f"{green}[ OK ]: Session unlocked.{reset}")
    return 0


def cmd_ls(args: List[str]) -> int:
    """ls — list files in the current directory (with color coding)."""
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
        print(f"Error: {e}\n")
        return 1
    return 0


def cmd_cat(args: List[str]) -> int:
    """cat <file> — print the contents of a text file."""
    if not args:
        print("Specify a file.\n")
        return 2
    try:
        with open(args[0], "r", encoding="utf-8", errors="ignore") as f:
            print(f"\n--- {args[0]} ---\n{f.read()}\n----------------\n")
    except Exception as e:  # noqa: BLE001
        print(f"Error: {e}\n")
        return 1
    return 0


def cmd_cd(args: List[str]) -> int:
    """
    cd [path] — change the working directory.

    IMPORTANT: _try_builtin() in core.shell_utils.run_command() fires
    EARLIER than the hardcoded branch `if argv[0] == "cd":` (run_command:322).
    Therefore, if `cd` is registered as a builtin (which we do), our handler
    shadows the built-in and must repeat its logic: expand `~`, update
    VariableStore.PWD, and handle errors correctly.
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
        print(f"cd: no such directory: {target}\n")
        return 1
    except OSError as e:
        print(f"cd: {e}\n")
        return 1
    return 0


# ===========================================================================
# Handler registry
# ===========================================================================

BUILTIN_HANDLERS = {
    # Basic Citadel commands (help/clear/fetch override the lighter
    # versions from core.repl._register_default_builtins).
    "help":    cmd_help,
    "fetch":   cmd_fetch,
    "clear":   cmd_clear,
    # System
    "center":  cmd_center,
    "pkg":     cmd_pkg,
    "netscan": cmd_netscan,
    "ping":    cmd_ping,
    "ip":      cmd_ip,
    "sysmon":  cmd_sysmon,
    "ps":      cmd_ps,
    "kill":    cmd_kill,        # ← override: PID, not jkill
    "df":      cmd_df,
    "free":    cmd_free,
    "files":   cmd_files,
    "notes":   cmd_notes,
    "crypto":  cmd_crypto,
    "passgen": cmd_passgen,
    "launcher": cmd_launcher,
    "recovery": cmd_recovery,
    "history": cmd_history,     # ← override: legacy format
    "weather": cmd_weather,
    "geo":     cmd_geo,
    "log":     cmd_log,
    "alias":   cmd_alias,       # ← override: legacy format
    "lock":    cmd_lock,
    "ls":      cmd_ls,
    "cd":      cmd_cd,          # ← no-op: real cd lives in run_command()
    "cat":     cmd_cat,
    # exit/q/quit are NOT registered — core.repl keeps them (sentinel -1).
}

def register_all(shell_utils_module) -> None:
    """
    Register all handlers from BUILTIN_HANDLERS in shell_utils.
    """
    # 1. Register the main command array from the dictionary
    for name, handler in BUILTIN_HANDLERS.items():
        shell_utils_module.register_builtin(name, handler)

    # 2. Register our new system condition command outside the loop
    shell_utils_module.register_builtin("[[", cmd_test_brackets)
    # Register true and false
    shell_utils_module.register_builtin("true", cmd_true)
    shell_utils_module.register_builtin("false", cmd_false)


def cmd_test_brackets(args: list[str]) -> bool:
    """
    Built-in command [[ ... ]] for condition testing.
    Called as: [[ -f file ]] or [[ X -gt 5 ]]
    """
    if not args:
        return False

    # Reassemble all arguments back into a single condition string.
    # If there's a trailing closing bracket ']]', strip it off.
    cond_str = " ".join(args)
    if cond_str.endswith("]]"):
        cond_str = cond_str[:-2].strip()

    # Run our condition engine
    result = eval_test_condition(cond_str)

    # Return True/False to the shell logic
    return result

def cmd_true(args: list[str]) -> int:
    """Built-in true command: always returns 0 (success)."""
    return 0

def cmd_false(args: list[str]) -> int:
    """Built-in false command: always returns 1 (error)."""
    return 1
