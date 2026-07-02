# Tests for Citadel OS (Phase 0.8)

This directory contains the unit-test suite for `core/` modules.

## Quick start

```bash
# Smoke: всё что есть
pytest

# С coverage
pytest --cov=core --cov-report=term-missing
```

## Layout

| File | Covers |
|---|---|
| `conftest.py` | Syspath bootstrap, autouse reset of singletons, fixtures |
| `test_shell_tokenizer.py` | Lexer, operators, quotes, escape, multiline-detectors |
| `test_shell_state.py` | VariableStore: CRUD, $VAR expansion, export, validation |
| `test_shell_history.py` | HistoryManager: begin/finish, recent/search/clear, JSONL persist |
| `test_shell_alias.py` | AliasEngine: normalize (3 formats), expand (variadic/positional), recursion |
| `test_shell_glob.py` | POSIX glob: `*`, `?`, `[abc]`, `**`, dotfiles |
| `test_repl.py` | build_prompt, process_line, HistoryBridge, run_repl_non_interactive, **build_banner (Phase 1.8)** |

## Conventions

- **No mocks for stdlib subprocess** — тесты с реальными процессами (`python -c "..."`) идут
  в категории "медленные", но дают настоящую уверенность что пайплайн не сломан.
- **tmp_path / monkeypatch** для всего что трогает реальные файлы.
- **autouse-фикстура `reset_citadel_singletons`** в conftest.py сбрасывает все
  known stateful singletons между тестами.
- **Тесты, которые могут оставить фоновый процесс** (subprocess.Popen с
  `&` в shell), помечены маркером `slow` и пропускаются на CI через
  `pytest -m "not slow"`.

## Adding a new test module

1. Файл `tests/test_<module>.py` — имя должно совпадать с тестируемым `core/`.
2. Импортируй `from core.<module> import ...` (syspath настроен в conftest).
3. Используй фикстуры `tmp_history`, `fresh_store`, `isolated_config` где применимо.
4. Не запускай `readline`-зависимые тесты с `run_repl()` напрямую — используй
   `run_repl_non_interactive(input_stream)` (test-friendly обёртка).

## Coverage

Цель — **> 70%** для `core/shell_*.py`. Покрытие UI / `repl.py run_repl()` —
неполное по дизайну (там нужен интеграционный smoke).
