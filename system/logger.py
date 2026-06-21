"""
Модуль логирования действий пользователя в Citadel OS.

Записывает все команды, а также критические события (вход/выход, ошибки авторизации)
в system/citadel.log. Ротация по размеру — при превышении MAX_BYTES старый файл
переименовывается в citadel.log.1 и начинается новый.
"""
import os
import time
from datetime import datetime

LOG_PATH = "system/citadel.log"
MAX_BYTES = 512 * 1024  # 512 KiB — предел, после которого лог ротируется
BACKUP_COUNT = 3  # хранить до 3 архивных логов


def _rotate_if_needed() -> None:
    """Если лог слишком большой — сдвигаем архивы (citadel.log.3 удаляется)."""
    if not os.path.exists(LOG_PATH):
        return
    try:
        if os.path.getsize(LOG_PATH) < MAX_BYTES:
            return
        # Сдвигаем архивы с конца
        for i in range(BACKUP_COUNT, 0, -1):
            src = f"{LOG_PATH}.{i}"
            dst = f"{LOG_PATH}.{i + 1}"
            if os.path.exists(src):
                if i == BACKUP_COUNT:
                    os.remove(src)
                else:
                    os.replace(src, dst)
        os.replace(LOG_PATH, f"{LOG_PATH}.1")
    except OSError:
        # Если не получилось — продолжаем писать в текущий файл
        pass


def log_event(level: str, message: str) -> None:
    """
    Записать событие в лог.
    level: "INFO", "WARN", "ERROR", "SECURITY"
    """
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        _rotate_if_needed()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] [{level.upper():<8}] {message}\n")
    except OSError:
        # Логирование не должно ломать основную работу
        pass


def log_command(command: str) -> None:
    """Логировать выполненную команду пользователя."""
    # Не логируем служебные пустые строки
    if command and command.strip():
        log_event("INFO", f"CMD: {command}")


def log_security(message: str) -> None:
    """Логировать событие безопасности (вход, смена пароля, неудачная попытка)."""
    log_event("SECURITY", message)


def log_error(message: str) -> None:
    """Логировать ошибку."""
    log_event("ERROR", message)


def tail_log(lines: int = 20) -> list[str]:
    """Вернуть последние N строк лога (для команды log)."""
    if not os.path.exists(LOG_PATH):
        return []
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            content = f.readlines()
        return [line.rstrip() for line in content[-lines:]]
    except OSError:
        return []
