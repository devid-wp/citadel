# FILE: core/shell_glob.py
# Citadel OS — POSIX-совместимый glob expansion для командной строки.
#
# Поддерживаемые паттерны (полностью POSIX, по glob(7)):
#   *              — любая последовательность символов (включая пустую), без /
#   ?              — любой один символ, не считая /
#   [abc]          — один символ из набора
#   [a-z]          — один символ из диапазона
#   [!abc] / [^a..] — отрицание набора (как в bash)
#   ** / *.py      — рекурсивный поиск (любой уровень вложенности)
#
# Что НЕ реализуем (вне scope):
#   - extglob (+(pat), *(pat), @(pat)) — bash extension, отдельная фича
#   - brace expansion ({a,b,c}) — это pre-tokenization уровень, не здесь
#   - tilde expansion (~/) — это VariableStore расширит
#
# Семантика:
#   - Каждый word-токен, содержащий glob-символы (* ? [), подменяется списком
#     совпадающих файлов в текущей директории (или относительно cwd).
#   - Если ничего не найдено — слово остаётся как есть (POSIX-стиль "по умолчанию").
#   - Quote-выражения (имеющие has_quotes=True) НЕ разворачиваются.
#
# Зависимости: только stdlib (fnmatch, os).

from __future__ import annotations

import os
from typing import List

from .shell_tokenizer import Token


# Символы, наличие которых означает "это glob-паттерн".
_GLOB_CHARS = set("*?[")


def is_glob(token: Token) -> bool:
    """Является ли токен glob-паттерном (и не взят в кавычки)."""
    if token.kind != "word":
        return False
    if token.has_quotes:
        return False
    return any(ch in _GLOB_CHARS for ch in token.value)


def _expand_simple(pattern: str, *, dotfiles: bool = False) -> List[str]:
    """Простой glob без ** (только текущая директория)."""
    import fnmatch

    base_dir, _, name_pat = pattern.rpartition("/")
    base_dir = base_dir or "."
    if not os.path.isdir(base_dir):
        return [pattern]

    try:
        entries = os.listdir(base_dir)
    except OSError:
        return [pattern]

    matches: List[str] = []
    for entry in entries:
        if not dotfiles and entry.startswith("."):
            continue
        if fnmatch.fnmatchcase(entry, name_pat):
            full = os.path.join(base_dir, entry) if base_dir != "." else entry
            matches.append(full)

    matches.sort()
    return matches if matches else [pattern]


def _expand_doublestar(pattern: str, *, dotfiles: bool) -> List[str]:
    """Glob с ** (рекурсивный обход директорий).

    Поддерживаемые формы:
        **/*.py        — все *.py в текущей и подпапках
        dir/**/*.py    — все *.py в dir/ и его подпапках
    """
    import fnmatch

    # Разбираем pattern: всё до /** — это prefix, всё после — суффикс.
    if "/**/" in pattern:
        prefix, suffix = pattern.split("/**/", 1)
        prefix = prefix or "."
        name_pat = suffix or "*"
    elif pattern.startswith("**/"):
        prefix = "."
        name_pat = pattern[3:] or "*"
    else:
        # ** без слэша — обычный single-level glob.
        return _expand_simple(pattern, dotfiles=dotfiles)

    if not os.path.isdir(prefix):
        return [pattern]

    matches: List[str] = []

    def _walk(directory: str) -> None:
        try:
            entries = os.listdir(directory)
        except OSError:
            return
        for entry in entries:
            if not dotfiles and entry.startswith("."):
                continue
            full = os.path.join(directory, entry) if directory != "." else entry
            if fnmatch.fnmatchcase(entry, name_pat):
                matches.append(full)
            if os.path.isdir(full):
                _walk(full)

    _walk(prefix)
    matches.sort()
    return matches if matches else [pattern]


def _expand_pattern(pattern: str, *, dotfiles: bool = False) -> List[str]:
    """
    Развернуть один паттерн в список файлов.

    Args:
        pattern: glob-паттерн (например, "*.py", "src/**/*.txt").
        dotfiles: если True — включает файлы начинающиеся с точки.

    Returns:
        Список совпадающих путей; если ничего не найдено — [pattern] (POSIX).
    """
    if "**" in pattern:
        return _expand_doublestar(pattern, dotfiles=dotfiles)
    return _expand_simple(pattern, dotfiles=dotfiles)


def expand_token(token: Token, *, cwd: str | None = None) -> List[Token]:
    """
    Развернуть glob-паттерн в один токен в список токенов.

    Если токен не glob — возвращает [token] без изменений.
    Если glob — возвращает по Token'ну на каждый файл (kind='word', has_quotes=False).

    Args:
        token: входной Token.
        cwd: рабочая директория (None = os.getcwd()).

    Returns:
        Список Token'ов (1+ элементов).
    """
    if not is_glob(token):
        return [token]

    old_cwd = None
    if cwd and cwd != os.getcwd():
        old_cwd = os.getcwd()
        try:
            os.chdir(cwd)
        except OSError:
            old_cwd = None

    try:
        paths = _expand_pattern(token.value)
    finally:
        if old_cwd:
            try:
                os.chdir(old_cwd)
            except OSError:
                pass

    out: List[Token] = []
    for p in paths:
        out.append(Token(
            raw=token.raw, value=p, kind="word", has_quotes=False,
            line=token.line, col=token.col,
        ))
    return out


def expand_tokens(tokens: List[Token], *, cwd: str | None = None) -> List[Token]:
    """
    Развернуть glob-паттерны во всех токенах.

    Args:
        tokens: список токенов после VariableStore.expand_tokens().
        cwd: рабочая директория.

    Returns:
        Плоский список токенов (модифицированной длины).
    """
    out: List[Token] = []
    for tok in tokens:
        if not is_glob(tok):
            out.append(tok)
            continue
        expanded = expand_token(tok, cwd=cwd)
        out.extend(expanded)
    return out