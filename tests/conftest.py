"""
Conftest для Citadel OS test-suite.

Задачи:
  1. Сделать корень проекта importable (chdir не нужен — pytest добавляет его).
  2. Изолировать stateful модули (history, store, signal ctx, job table)
     между тестами через autouse-фикстуру reset_state.
  3. Предоставить удобные фикстуры: tmp_history, isolated_config.
  4. Подавить шум (signal handlers не ставить, banner не печатать).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterator

import pytest

# Корень проекта — в sys.path, чтобы импорты core.* / system.* работали
# без хитростей с PYTHONPATH. pytest сам добавляет conftest.py-каталог,
# но для надёжности принудительно добавляем родителя /tests.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ----------------------------------------------------------------------------
# Глобальный autouse: сброс синглтонов между тестами
# ----------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def reset_citadel_singletons() -> Iterator[None]:
    """
    Сбрасывает все известные singleton'ы core.* после каждого теста.

    Зачем: VariableStore, HistoryManager, JobTable, SignalContext — все
    хранят глобальный state. Без сброса один тест может отравить другой.
    """
    yield
    # post-test cleanup
    try:
        from core import shell_history
        shell_history.reset_default_history()
    except Exception:
        pass
    try:
        from core import shell_state
        shell_state.reset_default_store()
    except Exception:
        pass
    try:
        from core import shell_jobs
        shell_jobs.reset_default_job_table()
    except Exception:
        pass
    try:
        from core import shell_signals
        shell_signals.reset_signal_context()
    except Exception:
        pass
    # Снести CITADEL_ALIAS_* env-переменные, что add_alias мог наставить
    for k in list(os.environ.keys()):
        if k.startswith("CITADEL_ALIAS_"):
            del os.environ[k]


# ----------------------------------------------------------------------------
# Фикстуры
# ----------------------------------------------------------------------------
@pytest.fixture
def tmp_history(tmp_path) -> Iterator:
    """
    Изолированный HistoryManager в tmp-файле. После теста — unlink.
    """
    from core.shell_history import HistoryManager
    p = tmp_path / "_citadel_hist.jsonl"
    h = HistoryManager(history_path=str(p))
    yield h
    try:
        p.unlink()
    except OSError:
        pass


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """
    Подменяет CONFIG_PATH в system.user_config на tmp-файл.
    Используется в тестах алиасов.
    """
    import system.user_config as uc
    monkeypatch.setattr(uc, "CONFIG_PATH", str(tmp_path / "user_config.json"))
    yield tmp_path


@pytest.fixture
def fresh_store():
    """Свежий VariableStore (не singleton)."""
    from core.shell_state import VariableStore
    return VariableStore()


# ----------------------------------------------------------------------------
# Подавление шума: pytest-cov печатает coverage в конце, не в каждом тесте.
# ----------------------------------------------------------------------------
def pytest_configure(config):
    """Регистрирует маркеры, чтобы pytest не ругался на -W."""
    config.addinivalue_line(
        "markers", "slow: помечает медленные тесты (с реальным subprocess)"
    )
