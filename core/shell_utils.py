"""
Вспомогательные утилиты командной оболочки Citadel.

Содержит:
  - CitadelCompleter: Tab-дополнение команд и алиасов (через встроенный readline).
  - resolve_command: подстановка алиасов из user_config.

На Windows модуль `readline` стандартной библиотеки недоступен —
используется pyreadline3 (если установлен). На Linux/macOS работает из коробки.
"""
import os

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


# Известные команды Citadel — для Tab-дополнения.
BUILTIN_COMMANDS = [
    "help", "fetch", "clear", "exit", "q", "center", "pkg", "netscan", "ping", "ip",
    "sysmon", "ps", "kill", "df", "free", "files", "notes", "crypto", "passgen",
    "launcher", "recovery", "history", "ls", "cd", "cat", "weather", "geo", "log",
    "alias", "lock",
]

# Слова для подсказки внутри интерактивных приложений (файловый браузер и т.д.)
APP_COMMANDS = {
    "files": ["cd", "view", "mkdir", "rm", "b"],
    "pkg": ["install", "remove", "search", "list", "update"],
}


class CitadelCompleter:
    """
    Completer для readline: дополняет первое слово — команды Citadel,
    последующие слова — пути к файлам.
    """

    def __init__(self):
        self.options = {
            "builtins": list(BUILTIN_COMMANDS),
            "aliases": list(get_aliases().keys()),
            "app": [c for cmds in APP_COMMANDS.values() for c in cmds],
        }

    def refresh(self):
        """Перечитать список алиасов из user_config (если пользователь их менял)."""
        self.options["aliases"] = list(get_aliases().keys())

    def _candidates(self, text: str) -> list[str]:
        words = self.options["builtins"] + self.options["aliases"] + self.options["app"]
        text = text.lower()
        return [w for w in words if w.startswith(text)]

    def complete(self, text: str, state: int):
        if readline is None:
            return None
        line = readline.get_line_buffer()
        parts = line.split()
        if not parts or (len(parts) == 1 and not line.endswith(" ")):
            # Дополняем первое слово — команду
            options = self._candidates(text)
        else:
            # Последующие слова — пути к файлам
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
        # Привязки клавиш: Tab дополняет, но не печатает сам '\t'
        readline.parse_and_bind("tab: complete")
        readline.parse_and_bind("set show-all-if-ambiguous on")
        readline.parse_and_bind("set bell-style none")
    except Exception:
        # Если что-то пошло не так — продолжаем без дополнения
        pass
    return completer


def resolve_command(user_input: str) -> str:
    """
    Подставить алиас, если введённая команда — алиас.
    Возвращает (возможно подставленную) команду.
    """
    parts = user_input.strip().split()
    if not parts:
        return user_input
    aliases = get_aliases()
    head = parts[0].lower()
    if head in aliases:
        rest = parts[1:]
        return " ".join([aliases[head]] + rest)
    return user_input
