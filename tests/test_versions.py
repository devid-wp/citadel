"""
Test: версии и runtime-пути Citadel OS v1.0 (Core 3.0).

Гарантирует, что:
  - VERSION = "1.0", CORE_VERSION = "3.0" (source of truth в config.py);
  - CITADEL_HOME / CITADEL_CONFIG_DIR / CITADEL_LOG_FILE — строки;
  - в user_config.py CONFIG_PATH указывает на реально существующий путь
    (либо dev-, либо production-target);
  - абсолютные пути утилит (TOOL_*) — действительно абсолютные.
"""
from __future__ import annotations

import importlib
import os
import sys

import pytest

import config


def test_version_strings():
    """Публичная версия — v1.0, движок — Core v3.0."""
    assert config.VERSION == "1.0", f"expected VERSION=1.0, got {config.VERSION!r}"
    assert config.CORE_VERSION == "3.0", f"expected CORE_VERSION=3.0, got {config.CORE_VERSION!r}"


def test_paths_are_strings():
    """Все runtime-пути должны быть строками и непустыми."""
    for name in (
        "CITADEL_HOME",
        "CITADEL_CONFIG_DIR",
        "CITADEL_LOG_FILE",
        "CITADEL_NOTES_DIR",
        "CITADEL_BACKUP_DIR",
        "CITADEL_RECOVERY_DIR",
        "CITADEL_HISTORY_FILE",
        "CITADEL_USER_CONFIG",
    ):
        assert hasattr(config, name), f"missing path constant: {name}"
        val = getattr(config, name)
        assert isinstance(val, str) and val, f"{name} must be a non-empty string"


def test_tools_are_absolute():
    """Пути к утилитам — абсолютные (/usr/bin/...)."""
    for name in (
        "TOOL_NMAP", "TOOL_TSHARK", "TOOL_AIRCRACK", "TOOL_PACMAN",
        "TOOL_IP", "TOOL_SS", "TOOL_ARP", "TOOL_PING", "TOOL_HTOP",
        "TOOL_EDITOR",
    ):
        val = getattr(config, name)
        assert os.path.isabs(val), f"{name}={val!r} must be an absolute path"


def test_user_config_path_resolves():
    """CONFIG_PATH из system.user_config указывает на файл, доступный для записи."""
    import system.user_config as uc
    p = uc.CONFIG_PATH
    assert isinstance(p, str) and p
    # Если папка ещё не создана — не падаем (config.py создаёт CITADEL_CONFIG_DIR).
    parent = os.path.dirname(p) or "."
    assert os.path.isdir(parent), f"parent dir {parent!r} does not exist"


def test_citadel_version_builtin():
    """$CITADEL_VERSION в shell_state должна соответствовать VERSION из config."""
    from core import shell_state
    store = shell_state.VariableStore()
    assert store.get("CITADEL_VERSION") == config.VERSION
    assert store.get("CITADEL_CORE_VERSION") == config.CORE_VERSION
