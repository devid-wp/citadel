"""
Citadel Shell — main entry point (v1.0, Core 3.0).

Structure:
  1. login_screen()                  — pre-REPL authentication.
  2. EnvAwarenessModule              — adaptive theme (HUD).
  3. install_completer()             — Tab completion.
  4. main_handlers.register_all()    — custom builtins.
  5. core.repl._register_default_builtins() — help/clear/exit/q/quit/fetch/jkill.
  6. REPL loop:
        while True:
            user_input = input(prompt)
            rc = run_command(user_input)   # ← single entry point
            if rc == -1: break             # ← sentinel from exit/q/quit
  7. atexit + sys.excepthook          — snapshot to ~/.citadel_recovery/ on crash.

All custom command logic (help, fetch, clear, center, pkg, ...) has moved
to main_handlers.py — only bootstrap and the loop live here.
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

# Custom Citadel builtins. Registered AFTER the defaults so that
# help/clear/fetch are overridden by the extended versions from main_handlers.
import core.shell_utils as _shell_utils
from main_handlers import register_all as _register_main_handlers, CMD_HISTORY


def main() -> None:
    # 1. Authentication
    login_screen()
    log_security("User logged in successfully")

    # 2. EnvAwarenessModule — daemon thread, updates theme based on time of day.
    #    Done BEFORE display_fastfetch() so the first render uses the
    #    actual palette. stop_all() is called in the finalizer.
    registry = get_registry()
    env_module = EnvAwarenessModule()
    registry.register(env_module)
    registry.start_all()
    log_security(
        f"EnvAwarenessModule started, current theme: "
        f"{get_theme_state().current_theme.value}"
    )

    # 3. Tab completion
    install_completer()

    # 4. Registering builtins.
    #    4a) core/repl._register_default_builtins() — help/clear/exit/q/quit/fetch/jkill.
    #    4b) main_handlers.register_all()           — extended Citadel commands
    #        (overrides help/clear/fetch; exit/q/quit left untouched).
    _register_default_builtins()
    _register_main_handlers(_shell_utils)

    # 4c. HistoryBridge — readline <-> HistoryManager.
    #     We need it to:
    #       • make ↑/↓ work in the interactive session (readline buffer);
    #       • persist ~/.citadel_history via HistoryManager.finish() →
    #         JSONL append (see core/shell_history.py:_append_to_disk);
    #       • on exit/Ctrl-D/EofError — bridge.close() does fsync +
    #         write_history_file for the readline buffer.
    bridge = HistoryBridge()
    bridge.setup_readline()

    # 4d. Recovery hooks (Phase 2.5):
    #       • atexit — snapshot on ANY normal exit (exit / return /
    #         Ctrl-D / unhandled exception not caught by try/except);
    #       • sys.excepthook — snapshot on an uncaught exception in the
    #         main thread (typical REPL crash).
    # install_recovery_hooks() returns a setter for cwd/history so we
    # can update them throughout the session.
    set_session_state = install_recovery_hooks(
        initial_cwd=os.getcwd(),
        recent_cmds=[],
    )
    # Make sure a snapshot also happens on a clean exit (exit/q/quit) — in
    # addition to excepthook. atexit does NOT fire on SIGKILL/SIGTERM,
    # but it does fire on sys.exit(), KeyboardInterrupt after the main
    # try, and a normal return.
    atexit.register(
        snapshot_session,
        reason=REASON_EXIT,
        cwd=os.getcwd(),
        recent_cmds_provider=lambda: list(CMD_HISTORY)[-20:],
    )

    # 5. Banner and fastfetch
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

    print(f"Citadel Shell v{config.VERSION} started successfully on top of "
          f"{sys.platform.capitalize()} Kernel.")
    print(f"Type {cyan}'help'{reset} to list extended utilities.")
    print(f"Use {cyan}Tab{reset} for command autocompletion and "
          f"the {cyan}↑/↓{reset} arrows for history.\n")

    # Greeting with geolocation (best-effort, no failure if no network).
    try:
        loc = get_location()
        if loc:
            print(f"{yellow}[ GEO ]{reset}: {loc.get('city', '—')}, "
                  f"{loc.get('country', '—')} ({loc.get('ip', '—')})  "
                  f"→ type {cyan}'weather'{reset} for the forecast.\n")
    except Exception:  # noqa: BLE001
        pass

    # 6. REPL loop. All command dispatch lives in run_command().
    while True:
        current_dir = os.getcwd()
        user_name = getattr(config, 'USER_NAME', 'User')
        prompt = f"{purple}[Citadel@{user_name} {os.path.basename(current_dir)}]$ {reset}"

        try:
            user_input = input(prompt).strip()
        except KeyboardInterrupt:
            print("\nUse 'exit' or 'q' to quit.")
            continue
        except EOFError:
            # Ctrl-D / end of pipe. Finish cleanly: bridge.close() will
            # save history, and the atexit hook will snapshot the session.
            print()
            break

        if not user_input:
            continue

        # Audit: write to the log + legacy list for cmd_history.
        log_command(user_input)
        CMD_HISTORY.append(user_input)
        set_session_state(
            cwd=os.getcwd(),
            recent_cmds=list(CMD_HISTORY)[-20:],
        )

        # HistoryBridge: every command is wrapped in begin/finish.
        # finish() writes a JSONL line to ~/.citadel_history right after
        # the command completes (see core/shell_history.py:_append_to_disk).
        # This means history is NOT lost even on kill -9 in the middle
        # of a session — the last written command is already on disk.
        handle = bridge.history.begin(user_input)
        try:
            rc = run_command(user_input)
        except Exception as e:  # noqa: BLE001
            print(f"{config.COLORS['RED']}Execution error:{config.COLORS['RESET']} {e}\n")
            rc = 1
        finally:
            bridge.history.finish(handle, exit_code=rc)
        bridge.add_readline(user_input)

        # Sentinel -1: exit (set by exit/q/quit through core/repl._register_default_builtins).
        if rc == -1:
            log_security("User exited Citadel Shell")
            clear_screen()
            terminal_print(
                "Shutting down Citadel Shell. Disconnecting terminal...",
                color_code=config.COLORS["RED"],
            )
            break

    # 7. Graceful shutdown. Save the readline buffer to file and fsync
    #    the JSONL history (in case of kill -9 right after return).
    try:
        bridge.close()
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # Ctrl-C right at the start (before login / before REPL) — clean
        # exit with a recovery snapshot.
        print("\n[ EXIT ]: Forced termination.")
        try:
            snapshot_session(
                reason=REASON_INTERUKPT,
                cwd=os.getcwd(),
                recent_cmds_provider=lambda: list(CMD_HISTORY)[-20:],
            )
        except Exception:  # noqa: BLE001
            pass
    except SystemExit:
        # sys.exit() from login_screen on auth failure. Re-raise, but
        # atexit will still run.
        raise
    except Exception as e:  # noqa: BLE001
        # Unhandled exception in main(). sys.excepthook has already
        # logged it and taken a snapshot; here we just print the traceback
        # to stderr for the user (in case excepthook didn't run yet —
        # e.g. in tests without interception).
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
        # Properly stop HUD modules. In case the process is interrupted
        # before main() finishes (Ctrl-C at the very start of the
        # session), get_registry() still returns the singleton with
        # registered modules.
        try:
            get_registry().stop_all()
        except Exception:  # noqa: BLE001
            pass
