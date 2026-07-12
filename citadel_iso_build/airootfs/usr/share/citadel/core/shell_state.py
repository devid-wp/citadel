# FILE: core/shell_state.py
# Citadel OS — Хранилище переменных shell-сессии.
#
# Хранит локальные переменные (`$FOO=bar`), умеет подставлять их
# в строки (`$FOO`, `${FOO}_x`), а также экспортировать в
# os.environ (тогда дочерние процессы тоже их видят).
#
# Зачем это в Citadel OS:
#   - `$NODE_ID`, `$THEME`, `$USER`, `$CWD` — встроенные переменные,
#     которые приложения apps/* ожидают как env.
#   - Временные переменные (`x = 123; echo $x`) — основа для будущих
#     conditional-скриптов.
#   - `export` пишет в os.environ, чтобы subprocesses видели переменные.
#
# Чистый stateful объект, без потоков. На сессию — один инстанс.

from __future__ import annotations

import os
import re
from typing import Dict, Iterable


# Встроенные переменные Citadel — инициализируются при первом get/set.
_BUILTINS: Dict[str, str] = {
    "CITADEL_VERSION": "3.0",
    "CITADEL_HOME": "",       # будет проставлено из os.path.expanduser("~")
    "CITADEL_PID": "",        # str(os.getpid())
    "USER": "",               # os.environ.get("USER", "citadel")
    "HOME": "",               # os.environ.get("HOME", "")
    "PWD": "",                # os.getcwd()
    "SHELL": "citadel",
}


class VariableStore:
    """
    Хранилище переменных + подстановка в строках.

    Использование:
        store = VariableStore()
        store.set("THEME", "purple")
        store.expand("theme is $THEME")    # → "theme is purple"
        store.set("NODE_ID", "7", export=True)  # попадёт в os.environ
    """

    # Разрешённые паттерны:
    #   $NAME        — NAME = [A-Za-z_][A-Za-z0-9_]*
    #   ${NAME}      — то же самое, но явно ограничено фигурными скобками
    _VAR_PATTERN = re.compile(
        r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)"
    )

    def __init__(self) -> None:
        self._vars: Dict[str, str] = {}
        self._initialize_builtins()

    # ------------------------------------------------------------------
    # Builtins
    # ------------------------------------------------------------------
    def _initialize_builtins(self) -> None:
        """Заполнить встроенные переменные актуальными значениями системы."""
        if not _BUILTINS["CITADEL_HOME"]:
            _BUILTINS["CITADEL_HOME"] = os.path.expanduser("~")
        if not _BUILTINS["CITADEL_PID"]:
            _BUILTINS["CITADEL_PID"] = str(os.getpid())
        if not _BUILTINS["USER"]:
            _BUILTINS["USER"] = os.environ.get("USER", "citadel")
        if not _BUILTINS["HOME"]:
            _BUILTINS["HOME"] = os.environ.get("HOME", os.path.expanduser("~"))
        if not _BUILTINS["PWD"]:
            _BUILTINS["PWD"] = os.getcwd()

        # Копируем во внутренний store (не затираем пользовательские значения).
        for k, v in _BUILTINS.items():
            if k not in self._vars and v:
                self._vars[k] = v

    def refresh_pwd(self, cwd: str) -> None:
        """Обновить $PWD после cd."""
        self._vars["PWD"] = cwd
        try:
            os.chdir(cwd)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # CRUD API
    # ------------------------------------------------------------------
    def get(self, name: str, default: str = "") -> str:
        """Получить значение переменной. Если нет — default."""
        if not name:
            return default
        # Сначала локальный store, потом os.environ.
        if name in self._vars:
            return self._vars[name]
        env_val = os.environ.get(name)
        if env_val is not None:
            return env_val
        return default

    def set(self, name: str, value: str, *, export: bool = False) -> None:
        """
        Установить значение переменной.

        Args:
            name: имя переменной.
            value: строковое значение.
            export: если True — продублировать в os.environ (видна дочерним процессам).
        """
        if not name or not _is_valid_name(name):
            raise ValueError(f"Invalid variable name: {name!r}")
        self._vars[name] = str(value)
        if export:
            os.environ[name] = str(value)

    def unset(self, name: str) -> bool:
        """Удалить переменную (и из os.environ если была экспортирована)."""
        removed = False
        if name in self._vars:
            del self._vars[name]
            removed = True
        if name in os.environ:
            del os.environ[name]
            removed = True
        return removed

    def all(self) -> Dict[str, str]:
        """Снимок всех переменных (включая экспортированные из os.environ)."""
        merged: Dict[str, str] = {}
        merged.update(os.environ)
        merged.update(self._vars)
        return merged

    # ------------------------------------------------------------------
    # Подстановка
    # ------------------------------------------------------------------
    def expand(self, text: str) -> str:
        """
        Раскрыть $VAR и ${VAR} в строке. Неизвестные переменные → пустая строка.

        Примеры:
            "echo $HOME"            → "echo /root"
            "x=${X}_end"            → "x=_end" (если X не задан)
            'literal "$HOME"'       → 'literal "$HOME"'  (не трогаем внутри '')
        """
        if not text or "$" not in text:
            return text

        def _replace(match: "re.Match[str]") -> str:
            name = match.group(1) or match.group(2)
            return self.get(name, "")

        return self._VAR_PATTERN.sub(_replace, text)

    def expand_tokens(self, tokens: Iterable) -> list:
        """Раскрыть переменные во всех word-токенах (остальные не трогаем)."""
        from .shell_tokenizer import Token  # локальный импорт — избегаем циклов
        out = []
        for tok in tokens:
            if tok.kind == "word":
                new_value = self.expand(tok.value)
                out.append(Token(
                    raw=tok.raw, value=new_value, kind=tok.kind,
                    has_quotes=tok.has_quotes, line=tok.line, col=tok.col,
                ))
            else:
                out.append(tok)
        return out

    # ------------------------------------------------------------------
    # Экспорт для subprocess
    # ------------------------------------------------------------------
    def as_env(self, extra: Dict[str, str] | None = None) -> Dict[str, str]:
        """
        Собрать окружение для subprocess.Popen: локальные переменные
        поверх os.environ. Если переменная помечена export — она уже там.
        """
        env = dict(os.environ)
        env.update(self._vars)
        if extra:
            env.update(extra)
        return env


def _is_valid_name(name: str) -> bool:
    """POSIX-совместимое имя переменной: буквы/цифры/_, начинается с буквы или _."""
    if not name:
        return False
    if not (name[0].isalpha() or name[0] == "_"):
        return False
    return all(c.isalnum() or c == "_" for c in name)


# Синглтон для удобства (опционально — можно создавать свои инстансы).
_default_store: VariableStore | None = None


def get_default_store() -> VariableStore:
    """Ленивый singleton — основной store для текущей shell-сессии."""
    global _default_store
    if _default_store is None:
        _default_store = VariableStore()
    return _default_store


def reset_default_store() -> None:
    """Сбросить singleton (для тестов и recovery)."""
    global _default_store
    _default_store = None