"""
Вспомогательные утилиты командной оболочки Citadel.

Содержит:
  - CitadelCompleter: Tab-дополнение команд и алиасов (через встроенный readline).
  - resolve_command: подстановка алиасов из user_config.
  - run_command: единая точка входа для выполнения пользовательской строки
    (tokenizer → variable expansion → alias expansion → pipeline → executor).

На Windows модуль `readline` стандартной библиотеки недоступен —
используется pyreadline3 (если установлен). На Linux/macOS работает из коробки.
"""
from __future__ import annotations

import os
import sys
import time
import json
from typing import List, Optional

# readline есть только на Unix. На Windows нужен pyreadline3 (pip install pyreadline3).
try:
    import readline
    _HAS_READLINE = True
except ImportError:
    try:
        import pyreadline3 as readline  # type: ignore
        _HAS_READLINE = True
    except ImportError:
        readline = None  # type: ignore
        _HAS_READLINE = False

try:
    from system.user_config import get_aliases
except ImportError:  # pragma: no cover
    def get_aliases():
        return {}

# Локальные импорты подсистем shell.
from .shell_tokenizer import (
    Token, TokenizeResult, tokenize,
    is_redirection, is_control, pretty_print_tokens,
)
from .shell_state import VariableStore, get_default_store
from .shell_alias import (
    AliasEntry, get_alias_map, expand_alias_tokens,
)
from .shell_history import HistoryManager, get_default_history
from .shell_pipeline import (
    PipelineStage, ParsedCommand, PipelineError,
    parse_pipeline, execute_pipeline, execute_commandline,
)


# Известные команды Citadel — для Tab-дополнения.
BUILTIN_COMMANDS = [
    "help", "fetch", "clear", "exit", "q", "center", "pkg", "netscan", "ping", "ip",
    "sysmon", "ps", "kill", "df", "free", "files", "notes", "crypto", "passgen",
    "launcher", "recovery", "history", "ls", "cd", "cat", "weather", "geo", "log",
    "alias", "lock",
    # Новое в v3.0:
    "set", "unset", "export", "vars", "env", "type",
]

# Слова для подсказки внутри интерактивных приложений (файловый браузер и т.д.)
APP_COMMANDS = {
    "files": ["cd", "view", "mkdir", "rm", "b"],
    "pkg": ["install", "remove", "search", "list", "update"],
}


# ============================================================================
# Tab-дополнение
# ============================================================================

class CitadelCompleter:
    """
    Completer для readline: дополняет первое слово — команды Citadel,
    последующие слова — пути к файлам.
    """

    def __init__(self):
        self.options = {
            "builtins": list(BUILTIN_COMMANDS),
            "aliases": [e.name for e in get_alias_map().values()],
            "app": [c for cmds in APP_COMMANDS.values() for c in cmds],
            "vars": ["$" + k for k in get_default_store().all().keys()],
        }

    def refresh(self):
        """Перечитать список алиасов и переменных (если пользователь их менял)."""
        self.options["aliases"] = [e.name for e in get_alias_map().values()]
        self.options["vars"] = ["$" + k for k in get_default_store().all().keys()]

    def _candidates(self, text: str) -> List[str]:
        words = (
            self.options["builtins"]
            + self.options["aliases"]
            + self.options["app"]
            + self.options["vars"]
        )
        text_l = text.lower()
        return [w for w in words if w.lower().startswith(text_l)]

    def complete(self, text: str, state: int):
        if readline is None:
            return None
        line = readline.get_line_buffer()
        parts = line.split()
        if not parts or (len(parts) == 1 and not line.endswith(" ")):
            options = self._candidates(text)
        else:
            try:
                options = [p for p in os.listdir(".") if p.startswith(text)]
            except OSError:
                options = []
        if state < len(options):
            return options[state]
        return None


def install_completer():
    """
    Установить completer и вернуть ссылку (для возможного refresh).
    Безопасно работает даже без модуля readline — Tab-дополнение будет просто отключено.
    """
    completer = CitadelCompleter()
    if not _HAS_READLINE or readline is None:
        return completer
    try:
        readline.set_completer(completer.complete)
        readline.parse_and_bind("tab: complete")
        readline.parse_and_bind("set show-all-if-ambiguous on")
        readline.parse_and_bind("set bell-style none")
    except Exception:
        pass
    return completer


# ============================================================================
# Alias resolution (legacy API)
# ============================================================================

def resolve_command(user_input: str) -> str:
    """
    Legacy: подставить алиас, если введённая команда — алиас.
    Возвращает (возможно подставленную) команду.
    """
    parts = user_input.strip().split()
    if not parts:
        return user_input
    alias_map = get_alias_map()
    expanded = expand_alias_tokens(parts, alias_map)
    return " ".join(expanded)


# ============================================================================
# НОВОЕ: единая точка входа run_command()
# ============================================================================

# Колбэки для интеграции с REPL (main.py).
_BUILTIN_HANDLERS: dict = {}


def register_builtin(name: str, handler) -> None:
    """
    Зарегистрировать builtin-команду (help, fetch, clear, ...).
    Handler signature: handler(args: list[str]) -> int (exit_code)
    """
    _BUILTIN_HANDLERS[name.lower()] = handler


def _try_builtin(argv: List[str]):
    """Если argv[0] — builtin, выполнить его и вернуть exit_code."""
    handler = _BUILTIN_HANDLERS.get(argv[0].lower())
    if handler is None:
        return None
    try:
        rc = handler(argv[1:]) or 0
        return int(rc)
    except SystemExit:
        raise
    except KeyboardInterrupt:
        return 130
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"citadel: builtin `{argv[0]}` failed: {e}\n")
        return 1


def run_command(
    raw_line: str,
    *,
    store: Optional[VariableStore] = None,
    history: Optional[HistoryManager] = None,
    on_line=None,
) -> int:
    """
    ЕДИНСТВЕННАЯ ТОЧКА ВХОДА для выполнения пользовательской команды.

    Конвейер:
        1. Tokenizer        — разбивка на токены.
        2. VariableStore    — раскрытие $VAR / ${VAR} в word-токенах.
        3. AliasEngine      — раскрытие первого токена если это алиас.
        4. Builtin dispatch — help/fetch/clear/etc.
        5. PipelineExecutor — внешняя команда через subprocess.Popen.
    """
    line = raw_line.rstrip("\n").rstrip("\r").strip()
    if not line:
        return 0

    # ----- Alias assignment: `name = body` -----
    if "=" in line and not line.startswith(("==", ">", "<")):
        first_tok, _, rest = line.partition("=")
        left = first_tok.strip()
        right = rest.strip()
        if (
            left
            and " " not in left
            and "|" not in line
            and ">" not in line and "<" not in line
            and ";" not in line
        ):
            from .shell_alias import add_alias
            try:
                add_alias(left, right)
                return 0
            except Exception as e:  # noqa: BLE001
                sys.stderr.write(f"citadel: cannot set alias: {e}\n")
                return 1

    # ----- Variable assignment: NAME=value -----
    if "=" in line and not line.startswith(("==", ">", "<")):
        first_tok, _, rest = line.partition("=")
        left = first_tok.strip()
        right = rest.strip()
        if (
            left
            and " " not in first_tok
            and "|" not in line
            and ">" not in line and "<" not in line
            and ";" not in line
        ):
            # Валидация имени: буквы/цифры/_, начинается с буквы или _.
            stripped = left.lstrip("$")
            if stripped and (stripped[0].isalpha() or stripped[0] == "_") \
                    and all(c.isalnum() or c == "_" for c in stripped):
                var_store = store or get_default_store()
                try:
                    export = False
                    if first_tok.strip().startswith("export "):
                        export = True
                        stripped = first_tok.strip()[len("export "):].strip().lstrip("$")
                    var_store.set(stripped, right, export=export)
                    return 0
                except ValueError as e:
                    sys.stderr.write(f"citadel: {e}\n")
                    return 1

    # ----- 1. Tokenize -----
    result = tokenize(line)
    if not result.tokens:
        return 0
    if result.errors:
        for err in result.errors:
            sys.stderr.write(f"citadel: {err.message}\n")

    # ----- 2. Variable expansion -----
    var_store = store or get_default_store()
    tokens = var_store.expand_tokens(result.tokens)

    # ----- 3. Alias expansion (первый токен) -----
    argv = [t.value for t in tokens if t.kind == "word"]
    argv = expand_alias_tokens(argv, get_alias_map())
    if not argv:
        return 0

    # ----- 3a. Builtin dispatch -----
    rc = _try_builtin(argv)
    if rc is not None:
        return rc

    # ----- 3b. cd -----
    if argv[0] == "cd":
        return _builtin_cd(argv[1:], var_store)

    # ----- 3c. history -----
    if argv[0] == "history":
        hist = history or get_default_history()
        n = 20
        if len(argv) > 1:
            try:
                n = int(argv[1])
            except ValueError:
                n = 20
        for entry in hist.recent(n):
            ts = time.strftime("%H:%M:%S", time.localtime(entry.ts))
            print(f"  {ts}  ({entry.exit_code:>3})  {entry.cmd}")
        return 0

    # ----- 3d. set / unset / export / vars / env -----
    if argv[0] == "set" and len(argv) >= 3:
        try:
            var_store.set(argv[1], argv[2], export=False)
            return 0
        except ValueError as e:
            sys.stderr.write(f"citadel: {e}\n")
            return 1

    if argv[0] == "unset" and len(argv) == 2:
        var_store.unset(argv[1])
        return 0

    if argv[0] == "export" and len(argv) >= 2:
        expr = argv[1]
        if "=" in expr:
            n, _, v = expr.partition("=")
            var_store.set(n, v, export=True)
        else:
            if expr in var_store.all():
                var_store.set(expr, var_store.get(expr), export=True)
        return 0

    if argv[0] == "vars":
        for k, v in sorted(var_store.all().items()):
            print(f"  {k}={v}")
        return 0

    if argv[0] == "env":
        for k, v in sorted(os.environ.items()):
            print(f"  {k}={v}")
        return 0

    if argv[0] == "type":
        return _builtin_type(argv[1:], var_store)

    # ----- 4. Pipeline execution -----
    pending = (history or get_default_history()).begin(line)
    try:
        flat_tokens = _flat_tokens_from_argv(argv, tokens)
        rc = execute_commandline(
            flat_tokens,
            env=var_store.as_env(),
            cwd=os.getcwd(),
            on_line=on_line,
        )
    except PipelineError as e:
        sys.stderr.write(f"citadel: {e}\n")
        rc = 127
    except KeyboardInterrupt:
        rc = 130
    except FileNotFoundError as e:
        sys.stderr.write(f"citadel: {e.filename or argv[0]}: command not found\n")
        rc = 127
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"citadel: unexpected error: {e}\n")
        rc = 1
    finally:
        (history or get_default_history()).finish(pending, exit_code=rc)

    return rc


def _builtin_cd(args: List[str], store: VariableStore) -> int:
    target = args[0] if args else os.path.expanduser("~")
    target = store.expand(target)
    try:
        os.chdir(target)
        store.refresh_pwd(os.getcwd())
        return 0
    except FileNotFoundError:
        sys.stderr.write(f"citadel: cd: no such directory: {target}\n")
        return 1
    except PermissionError:
        sys.stderr.write(f"citadel: cd: permission denied: {target}\n")
        return 1
    except NotADirectoryError:
        sys.stderr.write(f"citadel: cd: not a directory: {target}\n")
        return 1


def _builtin_type(args: List[str], store: VariableStore) -> int:
    import shutil
    if not args:
        sys.stderr.write("citadel: type: expected argument\n")
        return 2

    target = args[0]
    if target in _BUILTIN_HANDLERS:
        print(f"{target} is a citadel builtin")
        return 0

    alias_map = get_alias_map()
    if target in alias_map:
        entry = alias_map[target]
        print(f"{target} is an alias: {entry.body}")
        return 0

    path = shutil.which(target)
    if path:
        print(f"{target} is {path}")
        return 0

    print(f"{target}: not found", file=sys.stderr)
    return 1


def _flat_tokens_from_argv(
    argv: List[str],
    original_tokens: List[Token],
) -> List[Token]:
    """
    Восстановить плоский список токенов из argv (после алиаса) +
    операторов из оригинала. Костыль для merge — полноценный
    re-merge запланирован на следующую итерацию.
    """
    ops = [t for t in original_tokens if t.kind != "word"]
    out: List[Token] = []
    if not ops:
        for a in argv:
            out.append(Token(raw=a, value=a, kind="word"))
        return out

    for a in argv:
        out.append(Token(raw=a, value=a, kind="word"))
    out.extend(ops)
    return out