# FILE: core/shell_alias.py
# Citadel OS — Alias Engine v2.
#
# Что умеет новый движок:
#   - Обратная совместимость: legacy-формат {"ll": "ls -la"} → работает.
#   - Параметризация: "ll": "ls -la $@"   → ll /etc   =   ls -la /etc
#   - Позиционные:     "g":  "git $1 $@"   → g commit -m msg   =   git commit -m msg
#   - Поддержка цепочек через рекурсию: alias.g может вызывать другой алиас.
#
# Чего НЕ делает:
#   - Не парсит shell-операторы внутри body (|, >, ;) — это работа Tokenizer.
#   - Не подставляет переменные — этим занимается VariableStore (в body алиаса
#     мы раскрываем $@ и $N как позиционные, а $HOME обработает следующий слой).
#
# Хранение: user_config.get_aliases() возвращает dict. Поддерживаются оба формата:
#   - {"ll": "ls -la"}                        — legacy
#   - {"ll": {"body": "ls -la $@", "args": -1}} — расширенный
#   - {"ll": AliasEntry(body=..., arg_count=...)} — программный

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union


@dataclass
class AliasEntry:
    """Расширенная запись алиаса."""
    name: str
    body: str
    arg_count: int = -1      # -1 = вариативный ($@), 0..N = фиксированный

    def is_variadic(self) -> bool:
        return self.arg_count == -1


# Тип значения алиаса в user_config: строка (legacy) или AliasEntry (новый).
AliasValue = Union[str, AliasEntry, Dict]


def normalize_alias(raw_name: str, raw_value: AliasValue) -> AliasEntry:
    """
    Превратить любое представление алиаса (строка/dict/AliasEntry) в AliasEntry.

    Это ЕДИНСТВЕННАЯ точка конвертации legacy → v2. Все остальные модули
    работают с результатом этой функции.
    """
    if isinstance(raw_value, AliasEntry):
        return raw_value

    if isinstance(raw_value, str):
        return AliasEntry(name=raw_name, body=raw_value, arg_count=-1)

    if isinstance(raw_value, dict):
        body = raw_value.get("body") or raw_value.get("cmd") or ""
        args = raw_value.get("args", raw_value.get("arg_count", -1))
        try:
            args = int(args)
        except (TypeError, ValueError):
            args = -1
        return AliasEntry(name=raw_name, body=str(body), arg_count=args)

    raise ValueError(f"Unsupported alias value type for {raw_name!r}: {type(raw_value)}")


def get_alias_map() -> Dict[str, AliasEntry]:
    """
    Получить текущую карту алиасов из user_config и нормализовать.
    Если user_config недоступен — возвращаем пустой dict.
    """
    try:
        from system.user_config import get_aliases  # type: ignore
    except ImportError:
        return {}

    raw_map = get_aliases() or {}
    result: Dict[str, AliasEntry] = {}
    for name, value in raw_map.items():
        try:
            result[str(name)] = normalize_alias(str(name), value)
        except ValueError:
            # Сломанная запись — пропускаем, не валим shell.
            continue
    return result


def expand_alias_tokens(
    argv: List[str],
    alias_map: Optional[Dict[str, AliasEntry]] = None,
    *,
    _recursion_guard: int = 0,
) -> List[str]:
    """
    Развернуть первый токен (если это алиас) с подстановкой позиционных.

    Args:
        argv: токены после Tokenizer и VariableStore.expand_tokens.
        alias_map: предзагруженная карта. Если None — get_alias_map().
        _recursion_guard: защита от циклических алиасов.

    Returns:
        Развёрнутый список токенов.

    Цепочка `alias a = b; alias b = ls` → `a` → `b` → `ls`.
    """
    if _recursion_guard > 10:
        # Слишком глубокая вложенность — скорее всего цикл, возвращаем as-is.
        return argv

    if not argv:
        return argv

    if alias_map is None:
        alias_map = get_alias_map()

    head = argv[0]
    entry = alias_map.get(head)
    if entry is None:
        return argv

    # Раскрыть $@, $1..$9 в body. НЕ трогаем $HOME и т.п. — это VariableStore.
    body_tokens = entry.body.split() if entry.body else []
    user_args = argv[1:]

    expanded: List[str] = []
    for tok in body_tokens:
        if tok == "$@":
            expanded.extend(user_args)
        elif tok.startswith("$") and tok[1:].isdigit():
            idx = int(tok[1:]) - 1
            if 0 <= idx < len(user_args):
                expanded.append(user_args[idx])
            # Иначе — пустой токен, отбрасываем (как в bash).
        else:
            expanded.append(tok)

    # Рекурсия: первый токен результата тоже может быть алиасом.
    return expand_alias_tokens(
        expanded,
        alias_map,
        _recursion_guard=_recursion_guard + 1,
    )


def add_alias(name: str, body: str, *, arg_count: int = -1) -> None:
    """Добавить алиас в user_config (расширенный формат)."""
    try:
        from system.user_config import add_alias  # type: ignore
        add_alias(name, {"body": body, "args": arg_count})
    except ImportError:
        # Fallback: просто кладём в os.environ как CITADEL_ALIAS_<NAME>
        import os
        os.environ[f"CITADEL_ALIAS_{name.upper()}"] = body


def remove_alias(name: str) -> bool:
    """Удалить алиас. Возвращает True если был."""
    try:
        from system.user_config import remove_alias  # type: ignore
        return bool(remove_alias(name))
    except ImportError:
        import os
        key = f"CITADEL_ALIAS_{name.upper()}"
        if key in os.environ:
            del os.environ[key]
            return True
        return False