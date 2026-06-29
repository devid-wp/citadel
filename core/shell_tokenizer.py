# FILE: core/shell_tokenizer.py
# Citadel OS — Лексический анализатор командной строки.
#
# Назначение: превратить сырую строку пользователя в список Token'ов,
# сохранив семантику кавычек и экранирования. Никакой подстановки
# переменных здесь НЕТ — этим занимается VariableStore. Никакого
# раскрытия алиасов — это AliasEngine. Tokenizer — чистый лексер,
# состояние не хранит (singleton-free, stateless API).
#
# Поддерживает:
#   - Одинарные кавычки:  'hello $USER'   → литерал, $ не раскрывается
#   - Двойные кавычки:    "hello $USER"   → сохраняем '$' для VariableStore
#   - Экранирование:       \$, \\, \"     → следующий символ литерал
#   - Операторы:           |  |&  >  >>  <  2>  2>&1  ;  &
#   - Комментарии:         # ... до конца строки (только вне кавычек)
#
# Зависимости: ноль (pure stdlib).

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Literal


TokenKind = Literal[
    "word",            # любой "обычный" токен (аргумент)
    "pipe",            # |
    "pipe_err",        # |&
    "redir_out",       # >
    "redir_app",       # >>
    "redir_in",        # <
    "redir_err",       # 2>
    "redir_merge",     # 2>&1
    "semicolon",       # ;
    "background",      # &
]


@dataclass
class Token:
    """Одна лексическая единица после разбора строки."""
    raw: str                    # как выглядел в исходной строке (с кавычками если были)
    value: str                  # очищенное значение (без обрамляющих кавычек, escape раскрыт)
    kind: TokenKind = "word"
    has_quotes: bool = False    # True если value был внутри '' или ""

    # Диагностика — нужно для подсветки ошибок парсинга позже.
    line: int = 1
    col: int = 0


@dataclass
class TokenizeError:
    """Нефатальная ошибка токенизации (несбалансированные кавычки)."""
    message: str
    position: int


@dataclass
class TokenizeResult:
    tokens: List[Token] = field(default_factory=list)
    errors: List[TokenizeError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


class _State:
    NORMAL = "normal"
    SQUOTE = "squote"        # внутри '...'
    DQUOTE = "dquote"        # внутри "..."
    ESCAPE = "escape"        # сразу после \ (NORMAL)
    ESCAPE_DQ = "escape_dq"  # сразу после \ (DQUOTE)


_OPERATOR_TABLE = {
    "|": "pipe",
    "|&": "pipe_err",
    ">": "redir_out",
    ">>": "redir_app",
    "<": "redir_in",
    "2>": "redir_err",
    "2>&1": "redir_merge",
    ";": "semicolon",
    "&": "background",
}


def tokenize(line: str) -> TokenizeResult:
    """
    Разобрать строку на токены.

    Args:
        line: сырая команда от пользователя (без завершающего \\n).

    Returns:
        TokenizeResult: список Token'ов + ошибки (если есть).
        Ошибки НЕ прерывают разбор — невалидные куски добавляются как word.
    """
    result = TokenizeResult()
    buf: List[str] = []
    raw_buf: List[str] = []      # что было в исходнике (для отладки)
    state = _State.NORMAL
    has_quotes = False

    col = 0

    def flush_word() -> None:
        """Закрыть текущий буфер как word-токен (если непустой)."""
        nonlocal buf, raw_buf, has_quotes
        if buf or raw_buf:
            value = "".join(buf)
            raw = "".join(raw_buf)
            result.tokens.append(Token(
                raw=raw, value=value, kind="word", has_quotes=has_quotes,
            ))
            buf = []
            raw_buf = []
            has_quotes = False

    i = 0
    n = len(line)

    while i < n:
        ch = line[i]
        col = i

        # --- Комментарий вне кавычек ---
        if state == _State.NORMAL and ch == "#":
            # Всё до конца строки — комментарий, отбрасываем.
            break

        # --- Операторы (порядок КРИТИЧЕН: 2>&1 > 2> >> > < |& |) ---
        if state == _State.NORMAL:
            # 1) Четырёхсимвольный оператор (только один — 2>&1).
            four = line[i:i + 4]
            if four == "2>&1":
                flush_word()
                result.tokens.append(Token(
                    raw=four, value=four, kind="redir_merge",
                ))
                i += 4
                continue
            # 2) Двухсимвольные: проверяем в явном порядке приоритетов.
            two = line[i:i + 2]
            if two == ">>":
                flush_word()
                result.tokens.append(Token(raw=two, value=two, kind="redir_app"))
                i += 2
                continue
            if two == "2>":
                flush_word()
                result.tokens.append(Token(raw=two, value=two, kind="redir_err"))
                i += 2
                continue
            if two == "|&":
                flush_word()
                result.tokens.append(Token(raw=two, value=two, kind="pipe_err"))
                i += 2
                continue
            # 3) Односимвольные операторы.
            if ch in ("|", ";", "&"):
                flush_word()
                result.tokens.append(Token(
                    raw=ch, value=ch,
                    kind="pipe" if ch == "|" else ("semicolon" if ch == ";" else "background"),
                ))
                i += 1
                continue
            if ch in (">", "<"):
                flush_word()
                result.tokens.append(Token(
                    raw=ch, value=ch,
                    kind="redir_out" if ch == ">" else "redir_in",
                ))
                i += 1
                continue

        # --- Пробелы разделяют слова только в NORMAL ---
        if state == _State.NORMAL and ch.isspace():
            flush_word()
            i += 1
            continue

        # --- Escape: \\ в NORMAL ---
        if state == _State.NORMAL and ch == "\\":
            state = _State.ESCAPE
            i += 1
            continue

        if state == _State.ESCAPE:
            buf.append(ch)
            raw_buf.append("\\" + ch)
            state = _State.NORMAL
            i += 1
            continue

        # --- Escape внутри "..." ---
        if state == _State.DQUOTE and ch == "\\":
            state = _State.ESCAPE_DQ
            i += 1
            continue

        if state == _State.ESCAPE_DQ:
            # Внутри двойных кавычек экранируем только \, ", $, `, newline
            if ch in ('\\', '"', '$', '`', '\n'):
                buf.append(ch)
                raw_buf.append("\\" + ch)
            else:
                # Оставляем \ как литерал + сам символ
                buf.append("\\" + ch)
                raw_buf.append("\\" + ch)
            state = _State.DQUOTE
            i += 1
            continue

        # --- Кавычки ---
        if state == _State.NORMAL and ch == "'":
            state = _State.SQUOTE
            has_quotes = True
            raw_buf.append("'")
            i += 1
            continue

        if state == _State.SQUOTE:
            if ch == "'":
                state = _State.NORMAL
                raw_buf.append("'")
            else:
                buf.append(ch)
                raw_buf.append(ch)
            i += 1
            continue

        if state == _State.NORMAL and ch == '"':
            state = _State.DQUOTE
            has_quotes = True
            raw_buf.append('"')
            i += 1
            continue

        if state == _State.DQUOTE:
            if ch == '"':
                state = _State.NORMAL
                raw_buf.append('"')
            else:
                buf.append(ch)
                raw_buf.append(ch)
            i += 1
            continue

        # --- Обычный символ в слове ---
        buf.append(ch)
        raw_buf.append(ch)
        i += 1

    # Конец цикла. Финализируем.
    if state == _State.SQUOTE:
        result.errors.append(TokenizeError(
            "Unterminated single quote (')", position=col,
        ))
    elif state == _State.DQUOTE:
        result.errors.append(TokenizeError(
            'Unterminated double quote (")', position=col,
        ))
    elif state in (_State.ESCAPE, _State.ESCAPE_DQ):
        result.errors.append(TokenizeError(
            "Trailing backslash at end of line", position=col,
        ))

    flush_word()
    return result


def is_redirection(kind: TokenKind) -> bool:
    """Помощник для парсера pipeline — какие токены являются редиректами."""
    return kind in ("redir_out", "redir_app", "redir_in", "redir_err", "redir_merge")


def is_control(kind: TokenKind) -> bool:
    """Какие токены разделяют команды/пайпы."""
    return kind in ("pipe", "pipe_err", "semicolon", "background")


def pretty_print_tokens(tokens: List[Token]) -> str:
    """Для отладки — напечатать токены списком."""
    lines = []
    for t in tokens:
        flags = []
        if t.has_quotes:
            flags.append("quoted")
        lines.append(f"  [{t.kind:>14}] {t.value!r}  raw={t.raw!r}  {','.join(flags)}")
    return "\n".join(lines)