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
from .shell_tokenizer import line_continues, continuation_reason
from .theme_state import get_theme_state
from .shell_signals import get_signal_context


# ============================================================================
# Конфигурация REPL
# ============================================================================

HISTORY_PATH = os.path.expanduser("~/.citadel_history")
HISTORY_MAXLEN = 500  # синхронизировано с HistoryManager default

EXIT_COMMANDS = frozenset({"exit", "q", "quit", ":q", ":x"})

# ----- Banner (Phase 1.8) -----------------------------------------------------
# Логотип Citadel: ASCII-арт из logo.txt + 3 последние команды из истории.
# При TTY-выводе — с ANSI-цветами; в не-интерактивном режиме — сухая версия.

_LOGO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "logo.txt",
)


def _read_logo_lines() -> list[str]:
    """Прочитать logo.txt. Возвращает пустой список если файл не найден."""
    try:
        with open(_LOGO_PATH, "r", encoding="utf-8") as f:
            return [line.rstrip("\n") for line in f]
    except OSError:
        return []


def _format_recent_commands(
    history: Optional[HistoryManager] = None,
    n: int = 3,
    *,
    width: int = 44,
    muted: str = "",
    accent: str = "",
    reset: str = "",
) -> list[str]:
    """
    Сформатировать последние N команд из истории в строки для banner'а.

    Каждая строка:  "  │  <N>. <cmd усечённый до width>              │"
    Если история пуста — показываем подсказку.

    Args:
        history: HistoryManager (None = default singleton).
        n: сколько последних команд показать.
        width: ширина поля под команду (в символах).
        muted/accent/reset: ANSI-коды для подсветки.
    """
    if history is None:
        try:
            history = get_default_history()
        except Exception:
            history = None

    if history is None:
        return [f"  │{' ' * (width + 2)}│"]

    try:
        recent = history.recent(n) if hasattr(history, "recent") else []
    except Exception:
        recent = []

    if not recent:
        # Пустая история — намекнём что можно набрать help.
        return [
            f"  │{muted}  (no commands yet — try 'help'){reset}"
            f"{' ' * max(0, width - 30)}│",
        ]

    out: list[str] = []
    for idx, entry in enumerate(recent, start=1):
        # recent() отдаёт новейшие первые; для banner нам нужно наоборот —
        # последняя команда снизу, чтобы взгляд скользил сверху вниз.
        cmd = entry.cmd.strip()
        # Усечение: оставляем хвост команды если слишком длинная.
        max_cmd = width - 6  # "<N>. " + хвост
        if len(cmd) > max_cmd:
            cmd = "..." + cmd[-(max_cmd - 3):]
        prefix = f"{idx}. "
        # ANSI-выделение номера (тонкий акцент).
        number = f"{accent}{prefix}{reset}"
        inner = f"  {number}{cmd}"
        # Добиваем пробелами до правой границы.
        # 2 пробела слева + 1 справа (внутри │ ... │).
        # Ширина рамки = width + 2 пробела по бокам + 2 символа '│'.
        pad = max(1, width - 2 - len(inner) + len(prefix) + len(reset) + len(accent))
        # Упрощённо: считаем видимую длину без ANSI.
        visible = 2 + len(prefix) + len(cmd)
        pad = max(1, width + 2 - visible)
        out.append(f"  │{inner}{' ' * pad}│")
    return out


def build_banner(
    *,
    palette=None,
    history: Optional[HistoryManager] = None,
    n_recent: int = 3,
    is_tty: bool = True,
    use_color: bool = True,
) -> str:
    """
    Собрать полный banner для вывода при старте REPL.

    Структура:
        ┌──────────────────────────────────────────────┐
        │   <логотип Citadel из logo.txt, если есть>   │
        │  CITADEL OS · Modular Core v3.0              │
        │                                              │
        │  Recent commands:                            │
        │    1. ls -la                                 │
        │    2. fetch weather                          │
        │    3. notes add "todo: ship phase 0.8"       │
        │                                              │
        │  Type 'help' for commands. Ctrl-D / 'exit'   │
        │  to quit.                                    │
        └──────────────────────────────────────────────┘

    Args:
        palette: ThemePalette (None = взять из theme_state).
        history: HistoryManager (None = singleton).
        n_recent: сколько последних команд показать.
        is_tty: True если REPL стартует в TTY.
        use_color: True если разрешены ANSI-коды (например False в pipe).
    """
    if palette is None:
        try:
            palette = get_theme_state().current_palette
        except Exception:
            palette = None

    # Цвета с fallback на config.COLORS.
    primary = (palette.primary if palette else config.COLORS.get("PURPLE", "")) if use_color else ""
    accent = (palette.accent if palette else config.COLORS.get("CYAN", "")) if use_color else ""
    muted = (palette.muted if palette else config.COLORS.get("GRAY", "")) if use_color else ""
    reset = (palette.reset if palette else config.COLORS.get("RESET", "")) if use_color else ""

    # Ширина баннера — 46 символов внутри (подогнано под logo.txt).
    W = 46

    # Шапка.
    top = f"{primary}  ┌{'─' * W}┐{reset}"
    sep = f"{primary}  │{' ' * W}│{reset}"
    bot = f"{primary}  └{'─' * W}┘{reset}"

    lines: list[str] = []
    lines.append(top)

    # Логотип: рисуем в рамке. Каждая строка лого обрезается/добивается.
    logo_lines = _read_logo_lines()
    if logo_lines:
        # logo.txt: первая строка пустая, потом ASCII, потом две строки
        # с явной надписью CITADEL OS. Возьмём только ASCII-арт (строки
        # 1..7 по индексу 0..6) — блок CITADEL OS нарисуем сами.
        art = [ln for ln in logo_lines[1:8] if ln.strip()]
        for art_line in art:
            # Срезаем до 46 видимых символов, дополняем пробелами.
            visible = art_line[:W]
            pad = W - len(visible)
            lines.append(
                f"{primary}  │{reset}{accent}{visible}{reset}{' ' * pad}{primary}│{reset}"
            )
    else:
        # Нет logo.txt — fallback на текстовую шапку.
        title = f"  CITADEL OS  -  Modular Core v{getattr(config, 'VERSION', '3.0')}"
        pad = W - len(title)
        lines.append(
            f"{primary}  │{reset}{accent}{title}{reset}{' ' * pad}{primary}│{reset}"
        )

    lines.append(sep)

    # Подпись версии + строка-разделитель.
    ver = f"CITADEL OS  -  Modular Core v{getattr(config, 'VERSION', '3.0')}"
    pad = W - len(ver)
    lines.append(
        f"{primary}  │{reset}  {accent}{ver}{reset}{' ' * pad}{primary}│{reset}"
    )
    lines.append(sep)

    # Recent commands header.
    header = f"{muted}Recent commands:{reset}"
    pad = W - 2 - len("Recent commands:")
    lines.append(
        f"{primary}  │{reset}  {header}{' ' * pad}{primary}│{reset}"
    )

    # 3 последние команды.
    for rline in _format_recent_commands(
        history=history, n=n_recent, width=W - 2, muted=muted, accent=accent, reset=reset,
    ):
        lines.append(f"{primary}{rline}{reset}")

    lines.append(sep)

    # Подсказка про help / exit.
    hint1 = f"{muted}Type 'help' for commands. Ctrl-D / 'exit' to quit.{reset}"
    hint2 = f"{muted}Tip: arrow keys for history, Tab for completion.{reset}"
    pad1 = W - 2 - len("Type 'help' for commands. Ctrl-D / 'exit' to quit.")
    pad2 = W - 2 - len("Tip: arrow keys for history, Tab for completion.")
    lines.append(
        f"{primary}  │{reset}  {hint1}{' ' * pad1}{primary}│{reset}"
    )
    lines.append(
        f"{primary}  │{reset}  {hint2}{' ' * pad2}{primary}│{reset}"
    )
    lines.append(bot)

    return "\n".join(lines)


# Старая BANNER-константа оставлена для обратной совместимости (используется
# в run_repl() при is_tty=False, где логотип не нужен). В интерактивном
# режиме теперь вызывается build_banner().
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
    continuation: bool = False,
    reason: str = "",
) -> str:
    """
    Собрать prompt-строку под текущую тему.

    Формат:
        <primary>[Citadel<v> @ <user> <basename(cwd)>]$ <reset>

    Цвет primary берётся из Palette (привязан к времени суток).
    Без ANSI-кодов получается читаемый fallback для не-терминального вывода.

    Args:
        continuation: True если REPL сейчас в multiline-режиме
                      (незакрытая кавычка / скобка / \\ на конце строки).
                      В этом случае возвращается короткий prompt «... ».
        reason: «quote» / «brackets» / «backslash» — для тонкой подсветки
                (например, в multiline-режиме меняем цвет на красный).
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
    red = config.COLORS.get("RED", "\033[31m")

    if continuation:
        # Multiline-режим: минималистичный prompt. Красный если что-то
        # синтаксически сломано (quote/backslash), обычный акцент для скобок.
        marker_color = red if reason in ("quote", "backslash") else accent
        return f"{marker_color}... {reset}"

    user = user_name or getattr(config, "USER_NAME", "user")
    ver = version or getattr(config, "VERSION", "3.0")
    cwd = cwd or os.getcwd()
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
    # Фаза 2: Job-control. External-имя `kill` занято main_handlers.cmd_kill
    # (завершение OS-процесса по PID), поэтому background-job kill
    # зарегистрирован под `jkill` — см. shell_utils.run_command() строки
    # 376-383 (fallback) и main_handlers.register_all() (override не нужен).
    shell_utils.register_builtin("jkill", shell_utils._builtin_kill)

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

    # 0a. Установка signal handlers (Ctrl-C → foreground proc; SIGTERM → shutdown).
    #     Делаем ДО readline, чтобы хендлеры были активны с момента входа в loop.
    try:
        sig_ctx = get_signal_context()
        sig_ctx.install_handlers()
    except Exception:
        sig_ctx = None

    # 1. Инициализация истории
    bridge = HistoryBridge()

    # 2. Tab-completion (если есть readline и пользователь не запретил)
    #    completer_ref хранится в замыкании — нужен для hot-reload алиасов (1.6).
    completer_ref = {"obj": None}
    if setup_completer:
        try:
            from .shell_utils import install_completer
            completer_ref["obj"] = install_completer()
        except Exception:
            completer_ref["obj"] = None
    bridge.setup_readline(completer=completer_ref["obj"])

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

    # 4. Banner (Phase 1.8: логотип + 3 последние команды из истории).
    if banner:
        try:
            if is_tty:
                palette_obj = None
                try:
                    palette_obj = theme_state.current_palette if theme_state else None
                except Exception:
                    palette_obj = None
                banner_text = build_banner(
                    palette=palette_obj,
                    history=bridge.history,
                    n_recent=3,
                    is_tty=is_tty,
                    use_color=True,
                )
                print(banner_text)
            else:
                # Non-TTY: сухой однострочный баннер без ANSI.
                print("  Citadel Shell v" + getattr(config, "VERSION", "3.0"))
        except UnicodeEncodeError:
            print("  Citadel Shell v" + getattr(config, "VERSION", "3.0"))
        except Exception:
            # Любой сбой при построении баннера — фоллбек на простой текст.
            print("  Citadel Shell v" + getattr(config, "VERSION", "3.0"))

    # 5. Loop
    _input = raw_input if raw_input is not None else input
    exit_code = 0
    # Multiline-буфер (1.5 + 1.7). Копим строки, пока line_continues() == True.
    ml_buffer: list[str] = []
    ml_reason: str = ""        # «quote» / «brackets» / «backslash» — для подсветки
    try:
        while True:
            # Собрать prompt. В multiline-режиме — короткий «... »
            # с красным цветом если что-то синтаксически сломано.
            palette = None
            try:
                palette = theme_state.current_palette if theme_state else None
            except Exception:
                palette = None
            try:
                prompt_str = build_prompt(
                    palette=palette,
                    continuation=bool(ml_buffer),
                    reason=ml_reason,
                )
            except Exception:
                prompt_str = "... " if ml_buffer else "citadel$ "

            # Прочитать команду (в не-интерактивном режиме input() бросит EOFError)
            try:
                if is_tty:
                    line = _input(prompt_str)
                else:
                    line = _input()
                    if line and not line.endswith("\n"):
                        line += "\n"
            except KeyboardInterrupt:
                # Ctrl-C в multiline — сбрасываем буфер, НО не выходим из shell.
                if ml_buffer:
                    ml_buffer.clear()
                    ml_reason = ""
                    print("\n  (multiline buffer cleared)")
                    continue
                # Ctrl-C на пустом prompt — не убиваем shell.
                print("\n  (interrupted — type 'exit' to quit)")
                continue
            except EOFError:
                # Ctrl-D / конец pipe. Если буфер непустой — сбрасываем
                # с предупреждением, иначе выходим.
                if ml_buffer:
                    print(f"\n  [ Citadel: dropped {len(ml_buffer)} buffered line(s) on EOF ]")
                    ml_buffer.clear()
                    ml_reason = ""
                    continue
                print()  # newline после prompt
                break

            line = line.rstrip("\n").rstrip("\r")

            # 1.5 + 1.7: multiline-накопление. Если строка требует
            # продолжения — кладём в буфер и крутимся дальше.
            if ml_buffer or line_continues(line):
                if ml_buffer:
                    # Это очередная строка для уже открытого выражения.
                    ml_buffer.append(line)
                else:
                    # Первая строка нового multiline-блока.
                    ml_buffer.append(line)

                # Пересчитываем reason на полном буфере (важно для скобок —
                # они могут закрыться только через несколько строк).
                combined = "\n".join(ml_buffer)
                ml_reason = continuation_reason(combined)

                if not line_continues(combined):
                    # Буфер завершён. Склеиваем и исполняем как одну команду.
                    full_line = combined
                    ml_buffer.clear()
                    saved_reason = ml_reason
                    ml_reason = ""

                    if not full_line.strip():
                        continue
                    bridge.add_readline(full_line)
                    handle = bridge.history.begin(full_line)
                    try:
                        rc = process_line(full_line)
                        if rc == -1:
                            break
                        exit_code = rc
                    except KeyboardInterrupt:
                        print("\n  (interrupted)")
                        rc = 130
                    finally:
                        bridge.history.finish(handle, exit_code=rc)
                # Иначе — ждём следующую строку.
                continue

            # 2. Обычный путь: одна строка = одна команда.
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

            # 1.6: hot-reload алиасов. После ЛЮБОЙ команды проверяем,
                # изменились ли алиасы на диске — если да, обновляем completer.
                try:
                    obj = completer_ref.get("obj")
                    if obj is not None and hasattr(obj, "refresh"):
                        obj.refresh()
                except Exception:
                    pass

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

        # Cleanup: прибить все ещё-running фоновые jobs, чтобы они не
        # остались зомби-процессами после выхода из REPL.
        try:
            from .shell_jobs import get_default_job_table
            table = get_default_job_table()
            n = table.kill_all_running(force=True)
            if n:
                print(f"  [ Citadel: terminated {n} background job(s) ]",
                      file=sys.stderr)
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
    # 1.5 + 1.7: multiline-накопление. Нужно и тут — `run_repl_non_interactive`
    # часто используется из тестов и скриптов.
    ml_buffer: list[str] = []
    for raw in input_stream:
        line = raw.rstrip("\n").rstrip("\r")
        # Пустые строки в multiline-режиме — игнорим, иначе — пропускаем
        # как no-op, как в обычном цикле.
        if ml_buffer:
            if line:
                ml_buffer.append(line)
        elif not line:
            continue

        # Если буфер непустой или строка требует продолжения — копим.
        if not ml_buffer and not line_continues(line):
            # Однострочная команда — обычный путь.
            h = bridge.history.begin(line)
            try:
                rc = process_line(line)
            finally:
                rec_rc = rc if rc != -1 else 0
                bridge.history.finish(h, exit_code=rec_rc)
            if rc == -1:
                break
            last_real_rc = rc
            continue

        # Многострочный путь.
        if not ml_buffer:
            ml_buffer.append(line)
        combined = "\n".join(ml_buffer)
        if line_continues(combined):
            # Ждём следующую строку.
            continue
        # Готово — исполняем склеенную команду.
        full = combined
        ml_buffer.clear()
        h = bridge.history.begin(full)
        try:
            rc = process_line(full)
        finally:
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
