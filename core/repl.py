# FILE: core/repl.py
# Citadel OS — REPL (Read-Eval-Print Loop).
#
# Фаза 1: интерактивный шелл с историей и динамическим prompt'ом.
#
# Что здесь есть:
#   - build_prompt(state)  — собрать prompt с темой ThemeState.
#   - HistoryBridge        — двухсторонний мост readline <-> HistoryManager.
#   - run_repl()           — главный цикл:
#       • читает строку через input() / readline
#       • подставляет алиасы
#       • зовёт core.shell_utils.run_command()
#       • ловит KeyboardInterrupt, EOFError
#       • обрабатывает "exit" / "q"
#
# Что НЕ здесь (отложено в Фазу 2/4):
#   - многострочный ввод (1.5) — нужен детект незакрытой кавычки в Tokenizer
#   - tab-completion (1.4) — уже есть в shell_utils.install_completer()
#   - hot-reload алиасов (1.6) — частично работает через refresh CitadelCompleter
#   - banner (1.8) — отложен
#
# Зависимости: только stdlib + локальные core.* модули.

from __future__ import annotations

import atexit
import os
import sys
import shutil
from typing import Optional

# readline — optional dep. На Linux/Mac есть в stdlib; на Windows нужен
# pyreadline3. Без него prompt остаётся работоспособным, просто без
# навигации ↑/↓ (input() всё равно вернёт строку).
try:
    import readline  # type: ignore
    _HAS_READLINE = True
except ImportError:
    try:
        import pyreadline3 as readline  # type: ignore  # noqa: F401
        _HAS_READLINE = True
    except ImportError:
        readline = None  # type: ignore
        _HAS_READLINE = False

import config
from .shell_history import HistoryManager, get_default_history
from .theme_state import get_theme_state


# ============================================================================
# Конфигурация REPL
# ============================================================================

HISTORY_PATH = os.path.expanduser("~/.citadel_history")
HISTORY_MAXLEN = 500  # синхронизировано с HistoryManager default

EXIT_COMMANDS = frozenset({"exit", "q", "quit", ":q", ":x"})

BANNER = (
    f"{config.COLORS.get('PURPLE', '')}"
    f"  ┌──────────────────────────────────────────────┐\n"
    f"  │  Citadel Shell v{config.VERSION:>14}                │\n"
    f"  │  Type 'help' for commands. Ctrl-D / 'exit' to quit.  │\n"
    f"  └──────────────────────────────────────────────┘"
    f"{config.COLORS.get('RESET', '')}"
)


# ============================================================================
# Prompt: динамический, реагирует на смену темы
# ============================================================================

def build_prompt(
    *,
    palette=None,
    cwd: Optional[str] = None,
    user_name: Optional[str] = None,
    version: Optional[str] = None,
) -> str:
    """
    Собрать prompt-строку под текущую тему.

    Формат:
        <primary>[Citadel<v> @ <user> <basename(cwd)>]$ <reset>

    Цвет primary берётся из Palette (привязан к времени суток).
    Без ANSI-кодов получается читаемый fallback для не-терминального вывода.
    """
    if palette is None:
        try:
            palette = get_theme_state().current_palette
        except Exception:
            palette = None

    primary = palette.primary if palette else config.COLORS.get("PURPLE", "")
    accent = palette.accent if palette else config.COLORS.get("CYAN", "")
    muted = palette.muted if palette else config.COLORS.get("GRAY", "")
    reset = palette.reset if palette else config.COLORS.get("RESET", "")

    user = user_name or getattr(config, "USER_NAME", "user")
    ver = version or getattr(config, "VERSION", "3.0")
    cwd = cwd or os.getcwd()
    # basename для короткого вида; full path опционален через THEME.
    base = os.path.basename(cwd) or cwd
    sep = f"{accent}@{reset}"

    return (
        f"{primary}[Citadel{sep}{ver} {user} {base}]{reset}{muted}$ {reset}"
    )


# ============================================================================
# HistoryBridge: readline ↔ HistoryManager
# ============================================================================

class HistoryBridge:
    """
    Двухсторонний мост между readline и HistoryManager.

    Readline хранит свою in-memory историю (для ↑/↓ в сессии) и
    персистит её на диск через readline.write_history_file(). Наш
    HistoryManager — отдельный кольцевой буфер + JSONL для логирования.

    Bridge делает три вещи:
        1. Загружает readline-историю с диска при старте.
        2. После каждой команды дописывает её в наш HistoryManager (для логов).
        3. На выходе — сливает обе истории обратно на диск (lr-merge).

    На платформах без readline класс деградирует до «только HistoryManager».
    """

    def __init__(
        self,
        readline_path: str = HISTORY_PATH,
        history: Optional[HistoryManager] = None,
    ) -> None:
        self.readline_path = readline_path
        self.history = history or get_default_history()
        self._loaded = self._load_readline_history()

    # ----- readline side -----

    def _load_readline_history(self) -> bool:
        """Прочитать ~/.citadel_history через readline API. Возвращает ok."""
        if not _HAS_READLINE or readline is None:
            return False
        try:
            readline.read_history_file(self.readline_path)
            return True
        except FileNotFoundError:
            return True   # OK — просто пусто
        except OSError:
            return False

    def setup_readline(self, completer=None) -> None:
        """Установить readline bindings (стрелки, history-search)."""
        if not _HAS_READLINE or readline is None:
            return
        try:
            readline.parse_and_bind("tab: complete")
            readline.parse_and_bind("set show-all-if-ambiguous on")
            readline.parse_and_bind("set bell-style none")
            # History navigation по стрелкам — readline уже делает это
            # автоматически, если есть записи в readline-буфере.
            readline.set_history_length(HISTORY_MAXLEN)
            if completer is not None:
                readline.set_completer(completer.complete)
        except Exception:
            pass

    def add_readline(self, line: str) -> None:
        """Добавить строку в readline-буфер (без записи на диск)."""
        if not _HAS_READLINE or readline is None:
            return
        try:
            readline.add_history(line)
        except Exception:
            pass

    def save_readline_history(self) -> None:
        """Слить readline-буфер в файл."""
        if not _HAS_READLINE or readline is None:
            return
        try:
            readline.write_history_file(self.readline_path)
        except OSError as e:
            print(f"  [history] write failed: {e}", file=sys.stderr)

    # ----- our HistoryManager side -----

    def log(self, line: str) -> None:
        """Добавить команду в наш HistoryManager (для логов и `history` builtin)."""
        self.history.begin(line)

    def finish(self, handle, exit_code: int) -> None:
        """Закрыть запись в HistoryManager."""
        self.history.finish(handle, exit_code=exit_code)

    # ----- shutdown -----

    def close(self) -> None:
        """Сохранить обе истории на диск."""
        self.history.flush()
        self.save_readline_history()


# ============================================================================
# Регистрация базовых builtin-команд
# ============================================================================

_BUILTINS_REGISTERED = False


def _register_default_builtins() -> None:
    """
    Зарегистрировать в shell_utils те builtin-команды, которые исторически
    жили в main.py (help/fetch/clear/exit). Без этого run_command() не
    знает что с ними делать и падает в «неизвестная команда».

    Регистрация происходит ОДИН РАЗ за сессию (флаг _BUILTINS_REGISTERED),
    повторные вызовы — no-op.
    """
    global _BUILTINS_REGISTERED
    if _BUILTINS_REGISTERED:
        return

    try:
        from . import shell_utils
    except Exception:
        return

    def _help(args):
        # Локальный help — список builtin'ов. Полноценная таблица
        # из core.interface.display_help() доступна через старый main.py.
        items = sorted(shell_utils._BUILTIN_HANDLERS.keys()) if hasattr(
            shell_utils, "_BUILTIN_HANDLERS"
        ) else []
        if not items:
            print("  (no builtins registered)")
            return 0
        print("  Citadel builtins:")
        for n in items:
            print(f"    {n}")
        return 0

    def _clear(args):
        try:
            os.system("cls" if os.name == "nt" else "clear")
        except OSError:
            pass
        return 0

    def _exit(args):
        # Маркер «пора выходить». REPL перехватывает rc == -1.
        return -1

    shell_utils.register_builtin("help", _help)
    shell_utils.register_builtin("clear", _clear)
    shell_utils.register_builtin("exit", _exit)
    shell_utils.register_builtin("q", _exit)
    shell_utils.register_builtin("quit", _exit)
    shell_utils.register_builtin("fetch", lambda args: (_clear(args), 0)[1])

    _BUILTINS_REGISTERED = True


# ============================================================================
# Главный цикл REPL
# ============================================================================

def process_line(
    line: str,
    *,
    store=None,
    history_bridge: Optional[HistoryBridge] = None,
) -> int:
    """
    Обработать одну строку ввода. Возвращает exit_code.

    Используется как внутри run_repl(), так и в тестах / скриптах.
    Не делает чтение из stdin, не печатает prompt — только исполняет.
    """
    # Зарегистрировать дефолтные builtin'ы (help/clear/exit) при первом вызове.
    _register_default_builtins()

    from .shell_utils import run_command, VariableStore  # local import чтобы не цикл
    if store is None:
        store = VariableStore() if False else None  # используем default
    line = line.rstrip("\n").rstrip("\r")
    if not line.strip():
        return 0
    # exit — отдельная ветка, чтобы не пробираться через run_command().
    if line.strip().lower() in EXIT_COMMANDS:
        return -1  # маркер "пора выходить"
    try:
        return run_command(line)
    except KeyboardInterrupt:
        # Внутри run_command мог быть поднят, но не пойман. Подстраховка.
        print()  # перевод строки после ^C
        return 130
    except EOFError:
        return -1


def run_repl(
    *,
    interactive: Optional[bool] = None,
    banner: bool = True,
    setup_completer: bool = True,
    raw_input=None,
) -> int:
    """
    Главный цикл REPL.

    Args:
        interactive: True/False форсирует режим. None → autodetect по sys.stdin.isatty().
        banner: печатать ли приветствие при старте.
        setup_completer: установить ли CitadelCompleter (Tab-дополнение).
        raw_input: callable(str) -> str. Позволяет тестам подменять input().
                   По умолчанию используется built-in input().
    """
    is_tty = sys.stdin.isatty() if interactive is None else interactive

    # 0. Регистрация базовых builtin'ов, которые раньше жили в main.py.
    #    Делаем это здесь, чтобы run_command() знал про help/fetch/clear/exit.
    _register_default_builtins()

    # 1. Инициализация истории
    bridge = HistoryBridge()

    # 2. Tab-completion (если есть readline и пользователь не запретил)
    completer = None
    if setup_completer:
        try:
            from .shell_utils import install_completer
            completer = install_completer()
        except Exception:
            completer = None
    bridge.setup_readline(completer=completer)

    # 3. Подписка на смену темы (модули могут перерисовывать prompt)
    theme_state = None
    try:
        theme_state = get_theme_state()
        # On change печатаем уведомление (опционально); prompt build сам
        # пересоберётся на каждой итерации.
        def _on_theme_change(theme, palette):
            if is_tty:
                # Лёгкий сигнал: цвет prompt уже учтён в build_prompt().
                pass
        theme_state.subscribe(_on_theme_change)
    except Exception:
        pass

    # 4. Banner
    if banner and is_tty:
        try:
            print(BANNER)
        except UnicodeEncodeError:
            print("  Citadel Shell v" + config.VERSION)
    elif banner:
        # При не-интерактивном запуске печатаем «сухой» banner без ANSI
        print("  Citadel Shell v" + getattr(config, "VERSION", "3.0"))

    # 5. Loop
    _input = raw_input if raw_input is not None else input
    exit_code = 0
    try:
        while True:
            # Собрать prompt
            palette = None
            try:
                palette = theme_state.current_palette if theme_state else None
            except Exception:
                palette = None
            try:
                prompt_str = build_prompt(palette=palette)
            except Exception:
                prompt_str = "citadel$ "

            # Прочитать команду (в не-интерактивном режиме input() бросит EOFError)
            try:
                if is_tty:
                    line = _input(prompt_str)
                else:
                    line = _input()
                    if line and not line.endswith("\n"):
                        line += "\n"
            except KeyboardInterrupt:
                # Ctrl-C на пустом prompt — не убиваем shell.
                print("\n  (interrupted — type 'exit' to quit)")
                continue
            except EOFError:
                # Ctrl-D / конец pipe.
                print()  # newline после prompt
                break

            line = line.rstrip("\n").rstrip("\r")
            if not line:
                continue

            # Дубликаты в readline: не пихать «тот же» 100 раз подряд
            bridge.add_readline(line)

            # Записать в наш HistoryManager
            handle = bridge.history.begin(line)

            # Исполнить
            try:
                rc = process_line(line)
                if rc == -1:
                    break
                exit_code = rc
            except KeyboardInterrupt:
                # Процесс прерван, но мы — нет.
                print("\n  (interrupted)")
                rc = 130
            finally:
                bridge.history.finish(handle, exit_code=rc)

    except KeyboardInterrupt:
        # Ctrl-C на самом глубоком уровне — сваливаем.
        print("\n  [ Citadel: forced exit ]")
        exit_code = 130

    finally:
        bridge.close()
        # Корректное завершение: atexit-хук для readline тоже сработает,
        # но явный close() гарантирует flush даже при KeyboardInterrupt.
        try:
            atexit.unregister(readline.write_history_file)  # noqa: F821
        except Exception:
            pass

    return exit_code


# ============================================================================
# Helpers для тестов
# ============================================================================

def run_repl_non_interactive(input_stream, *, banner: bool = False) -> int:
    """
    Специальная обёртка для тестов / скриптов: читает команды из file-like
    объекта (например, io.StringIO), не использует readline (всё равно
    бесполезен в pipe).

    Args:
        input_stream: iterable, отдающее строки (с \\n или без).
        banner: подавить банер (по умолчанию в тестах).

    Returns:
        Exit code последней выполненной команды.
    """
    _register_default_builtins()
    bridge = HistoryBridge()
    if not banner:
        # suppress banner
        pass
    last_real_rc = 0
    for raw in input_stream:
        line = raw.rstrip("\n").rstrip("\r")
        if not line:
            continue
        h = bridge.history.begin(line)
        try:
            rc = process_line(line)
        finally:
            # exit (-1) не записываем как реальный код — это маркер выхода
            rec_rc = rc if rc != -1 else 0
            bridge.history.finish(h, exit_code=rec_rc)
        if rc == -1:
            break
        last_real_rc = rc
    bridge.close()
    return last_real_rc


# ============================================================================
# CLI entry: `python -m core.repl` для ручного запуска REPL
# ============================================================================

if __name__ == "__main__":
    sys.exit(run_repl(interactive=True))
