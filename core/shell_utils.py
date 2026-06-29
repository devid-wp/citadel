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
from .shell_glob import expand_tokens as expand_glob_tokens


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


def expand_command(user_input: str) -> List[str]:
    """
    Раскрыть алиас в первой позиции и вернуть список токенов (List[str]).
    Полезно для тестов и интеграций, где нужно увидеть результат без исполнения.

    Args:
        user_input: сырая команда (например, "g commit msg").

    Returns:
        Список токенов после раскрытия алиаса (например, ["git", "commit", "msg"]).
    """
    parts = user_input.strip().split()
    if not parts:
        return []
    return expand_alias_tokens(parts, get_alias_map())


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

    # ----- Variable assignment: NAME=value (без операторов внутри) -----
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

    # ----- 2.5. Glob expansion — развернуть *.py и подобные в списки файлов -----
    tokens = expand_glob_tokens(tokens, cwd=os.getcwd())

    # ----- 3. Detect alias on first word (для последующего re-merge) -----
    original_first_word = ""
    for t in tokens:
        if t.kind == "word":
            original_first_word = t.value
            break

    argv = [t.value for t in tokens if t.kind == "word"]
    argv = expand_alias_tokens(argv, get_alias_map())
    if not argv:
        return 0

    # ----- 3.0. Re-merge: подменить первое слово на argv после алиаса -----
    if argv[0] != original_first_word and original_first_word:
        tokens = _remerge_after_alias(line, argv)

    # ----- 3a. Builtin dispatch -----
    rc = _try_builtin(argv)
    if rc is not None:
        return rc

    # ----- 3a-extra. alias builtin (list/add/remove) -----
    if argv[0] == "alias":
        return _builtin_alias(argv[1:])

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

    # ----- 3e. Background job management -----
    if argv[0] == "jobs":
        return _builtin_jobs(argv[1:])
    if argv[0] == "kill":
        return _builtin_kill(argv[1:])
    if argv[0] == "wait":
        return _builtin_wait(argv[1:])

    # ----- 4. Pipeline execution -----
    pending = (history or get_default_history()).begin(line)
    try:
        # tokens уже корректные (с re-merge операторов после алиаса).
        rc = execute_commandline(
            tokens,
            env=var_store.as_env(),
            cwd=os.getcwd(),
            on_line=on_line,
            raw_command=line,
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


def _builtin_jobs(args: List[str]) -> int:
    """
    Builtin `jobs` — список фоновых job'ов.

    Флаги:
        jobs       → только активные (running)
        jobs -l    → все (включая exited)
        jobs -a    → все
    """
    from .shell_jobs import get_default_job_table

    table = get_default_job_table()
    show_all = bool(args) and args[0] in ("-l", "-a", "--all")
    jobs = table.all() if show_all else table.running()

    if not jobs:
        print("  (no background jobs)")
        return 0

    print(f"  {'ID':>3}  {'PID':>7}  {'STATE':<10}  COMMAND")
    for j in jobs:
        marker = ""
        if j.state.value == "running":
            marker = "+"     # current
        elif j.state.value == "exited":
            marker = "-"
        print(f"  {j.job_id:>3}  {j.pid:>7}  {j.state.value:<10}  {j.command}")
    return 0


def _builtin_kill(args: List[str]) -> int:
    """
    Builtin `kill` — завершить фоновый job.

    Использование:
        kill <job_id>          → SIGTERM (terminate)
        kill -9 <job_id>       → SIGKILL (kill)
        kill -KILL <job_id>
    """
    from .shell_jobs import get_default_job_table

    if not args:
        sys.stderr.write("citadel: kill: expected job_id\n")
        return 2

    force = False
    if args[0].startswith("-") and args[0][1:].isdigit():
        if args[0] in ("-9", "-KILL", "-SIGKILL"):
            force = True
            args = args[1:]
        else:
            sys.stderr.write(f"citadel: kill: unknown signal {args[0]}\n")
            return 2

    if not args:
        sys.stderr.write("citadel: kill: expected job_id\n")
        return 2

    try:
        jid = int(args[0])
    except ValueError:
        sys.stderr.write(f"citadel: kill: invalid job_id: {args[0]!r}\n")
        return 2

    table = get_default_job_table()
    if table.kill(jid, force=force):
        print(f"  killed job [{jid}]")
        return 0
    print(f"  citadel: kill: job [{jid}] not found or not running", file=sys.stderr)
    return 1


def _builtin_wait(args: List[str]) -> int:
    """
    Builtin `wait` — дождаться завершения всех (или конкретного) job'ов.

    Использование:
        wait           → ждать ВСЕ фоновые jobs
        wait <job_id>  → ждать конкретного
    """
    from .shell_jobs import get_default_job_table

    table = get_default_job_table()

    if not args:
        # Ждём все.
        jobs = table.running()
        for j in jobs:
            table.wait(j.job_id)
        return 0

    try:
        jid = int(args[0])
    except ValueError:
        sys.stderr.write(f"citadel: wait: invalid job_id: {args[0]!r}\n")
        return 2

    rc = table.wait(jid)
    if rc is None:
        print(f"  citadel: wait: timeout or no job [{jid}]", file=sys.stderr)
        return 1
    return rc


def _builtin_alias(args: List[str]) -> int:
    """
    Builtin `alias` — управление алиасами.

    Поддерживает формы:
        alias                       → показать все
        alias list                  → то же самое
        alias NAME                  → показать конкретный (если есть)
        alias add NAME BODY         → добавить legacy
        alias add NAME BODY $@      → добавить расширенный (содержит $@)
        alias remove NAME           → удалить
        alias rm NAME               → удалить (псевдоним)
    """
    from .shell_alias import get_alias_map, add_alias as _add, remove_alias as _rm

    # Без аргументов / list → список
    if not args or args[0] in ("list", "-l", "ls"):
        mp = get_alias_map()
        if not mp:
            print("  (aliases empty - add: alias add ll 'ls -la $@')")
            return 0
        print("=== CITADEL ALIASES ===")
        for name in sorted(mp):
            entry = mp[name]
            body = entry.body
            arg_marker = " $@" if "$@" in body or any(
                f"${i}" in body for i in range(1, 10)
            ) else ""
            print(f"  {name:<14} -> {body}{arg_marker}")
        print()
        return 0

    # alias NAME → один алиас
    if len(args) == 1 and args[0] not in ("add", "remove", "rm", "del"):
        mp = get_alias_map()
        if args[0] in mp:
            e = mp[args[0]]
            print(f"  {args[0]} → {e.body}")
            return 0
        sys.stderr.write(f"citadel: alias: {args[0]}: not found\n")
        return 1

    # alias add NAME BODY...
    if args[0] in ("add", "set") and len(args) >= 3:
        name = args[1]
        body = " ".join(args[2:])
        try:
            _add(name, body)
            print(f"  [+] alias '{name}' -> '{body}'")
            return 0
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f"citadel: alias add failed: {e}\n")
            return 1

    # alias remove NAME
    if args[0] in ("remove", "rm", "del") and len(args) == 2:
        if _rm(args[1]):
            print(f"  [-] alias '{args[1]}' removed.")
            return 0
        sys.stderr.write(f"citadel: alias: {args[1]}: not found\n")
        return 1

    print("Использование:")
    print("  alias                         — список всех")
    print("  alias NAME                    — показать конкретный")
    print("  alias add NAME BODY           — добавить")
    print("  alias remove NAME             — удалить")
    return 2


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


def _remerge_after_alias(
    original_line: str,
    argv_after_alias: List[str],
) -> List[Token]:
    """
    Корректный re-merge операторов после раскрытия алиаса.

    Стратегия: подменить ПЕРВОЕ СЛОВО в исходной строке на раскрытое тело
    алиаса, оставив все остальные слова и операторы на своих местах.
    Затем ретокенизировать результат.

    Пример:
        input:   "g commit -m msg > log.txt"
        alias g: "git"
        merged:  "git commit -m msg > log.txt"
    """
    # Находим первое слово в строке (без учёта кавычек — нам нужен индекс).
    stripped = original_line.lstrip()
    if not stripped:
        return []

    # Ищем конец первого слова (до первого whitespace).
    end = 0
    while end < len(stripped) and not stripped[end].isspace():
        end += 1

    first_word = stripped[:end]
    rest = stripped[end:]   # с ведущим пробелом или пусто

    # Цитируем argv[0] если оно содержит спецсимволы.
    def _quote(s: str) -> str:
        if not s:
            return '""'
        if any(c.isspace() or c in '|<>&;"\\' for c in s):
            return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'
        return s

    new_first = " ".join(_quote(a) for a in argv_after_alias)
    merged = new_first + rest

    result = tokenize(merged)
    if result.errors:
        for err in result.errors:
            sys.stderr.write(f"citadel: {err.message}\n")
    return result.tokens