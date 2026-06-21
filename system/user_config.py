"""
Модуль пользовательских настроек Citadel OS.

Хранит пользовательские предпочтения (тема, имя, алиасы, последняя локация и т.д.)
в отдельном JSON-файле — system/user_config.json. Это позволяет менять настройки
без перезаписи config.py и не ломать исходный код при сбоях.
"""
import os
import json
import time
from typing import Any

CONFIG_PATH = "system/user_config.json"

_DEFAULTS = {
    "user_name": "User",
    "theme_color": "PURPLE",
    "text_delay": 0.002,
    "aliases": {
        "ll": "ls",
        "la": "ls",
        "c": "clear",
        "h": "history",
        "q": "exit",
    },
    "last_location": None,  # {"ip": "...", "city": "...", "country": "...", "lat": ..., "lon": ...}
    "favorite_city": None,
}


def _load_raw() -> dict:
    """Загружает JSON. Если файл не существует или повреждён — возвращает копию дефолтов."""
    if not os.path.exists(CONFIG_PATH):
        return _deepcopy_defaults()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Добиваем дефолтами недостающие ключи (для совместимости со старой версией)
        merged = _deepcopy_defaults()
        merged.update(data or {})
        return merged
    except (json.JSONDecodeError, OSError):
        return _deepcopy_defaults()


def _deepcopy_defaults() -> dict:
    """Глубокая копия словаря дефолтов (чтобы вложенные словари не шарились)."""
    import copy
    return copy.deepcopy(_DEFAULTS)


def _save_raw(data: dict) -> bool:
    """Атомарная запись JSON. Возвращает True при успехе."""
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        # Атомарность: пишем во временный файл, затем переименовываем
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(tmp, CONFIG_PATH)
        return True
    except OSError:
        return False


# === Публичный API ===

def get_user_pref(key: str, default: Any = None) -> Any:
    """Получить значение пользовательской настройки. Если ключ не существует — вернуть default."""
    data = _load_raw()
    return data.get(key, default)


def set_user_pref(key: str, value: Any) -> bool:
    """Установить значение пользовательской настройки и сохранить в файл."""
    data = _load_raw()
    data[key] = value
    return _save_raw(data)


def get_all() -> dict:
    """Получить весь словарь настроек (для диагностики)."""
    return _load_raw()


def get_aliases() -> dict[str, str]:
    """Получить словарь алиасов команд."""
    return dict(_load_raw().get("aliases") or {})


def add_alias(name: str, command: str) -> bool:
    """Добавить или обновить алиас."""
    if not name or not command:
        return False
    data = _load_raw()
    aliases = dict(data.get("aliases") or {})
    aliases[name] = command
    data["aliases"] = aliases
    return _save_raw(data)


def remove_alias(name: str) -> bool:
    """Удалить алиас."""
    data = _load_raw()
    aliases = dict(data.get("aliases") or {})
    if name in aliases:
        del aliases[name]
        data["aliases"] = aliases
        return _save_raw(data)
    return False


def cache_location(location: dict) -> bool:
    """
    Сохранить последнюю определённую локацию.
    location: {"ip", "city", "country", "lat", "lon", "timezone", ...}
    """
    if not isinstance(location, dict):
        return False
    location = dict(location)
    location["fetched_at"] = int(time.time())
    data = _load_raw()
    data["last_location"] = location
    return _save_raw(data)


def get_cached_location(max_age_seconds: int = 3600) -> dict | None:
    """
    Получить закэшированную локацию, если она не старше max_age_seconds.
    Иначе возвращает None — caller должен запросить заново.
    """
    loc = _load_raw().get("last_location")
    if not isinstance(loc, dict):
        return None
    age = int(time.time()) - int(loc.get("fetched_at", 0))
    if age > max_age_seconds:
        return None
    return loc
