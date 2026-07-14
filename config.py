# Citadel OS v1.0 — Global Configuration
#
# Source of truth для всех версий системы:
#   VERSION       — публичная версия релиза (display only).
#   CORE_VERSION  — версия внутреннего движка (shell + recovery + history).
# Любые модули должны читать обе константы отсюда, а не хардкодить.

VERSION = "1.0"
CORE_VERSION = "3.0"

USER_NAME = "User"
SHELL_PROMPT = "CitadelOS @ User $> "

# Пароль для входа (по умолчанию: admin)
# MD5("admin") оставлен как legacy-fallback для уже сгенерённых rootfs.
# При первом логине пользователь должен сменить его (см. core/auth.py).
PASSWORD_HASH = "21232f297a57a5a743894a0e4a801fc3"

COLORS = {
    "PURPLE": "\033[95m",
    "CYAN": "\033[96m",
    "DARK_CYAN": "\033[36m",
    "BLUE": "\033[94m",
    "GREEN": "\033[92m",
    "YELLOW": "\033[93m",
    "RED": "\033[31m",
    "GRAY": "\033[90m",
    "RESET": "\033[0m",
}

# Текущая тема оформления (по умолчанию PURPLE)
THEME_COLOR = "PURPLE"

TEXT_DELAY = 0.002
DEBUG_MODE = False


# ============================================================================
# Runtime paths. Все абсолютные пути — для rootfs /opt/citadel/.
# В dev-режиме (на хосте) подменяются на repo-local пути через _resolve_*.
# ============================================================================
import os
import sys

_DEV_MODE = os.environ.get("CITADEL_DEV") == "1" or not os.path.isdir("/opt/citadel")

def _resolve(opt_path: str, dev_path: str) -> str:
    """Если /opt/citadel существует и не dev-режим — opt_path, иначе dev_path."""
    if _DEV_MODE:
        return dev_path
    return opt_path if os.path.isabs(opt_path) else os.path.join("/opt/citadel", opt_path.lstrip("/"))


# Базовая директория Citadel. В production — /opt/citadel/, в dev — корень репо.
CITADEL_HOME = "/opt/citadel" if not _DEV_MODE else os.path.dirname(os.path.abspath(__file__))

# Конфиги и runtime-state (логи, recovery-snapshots, история, заметки).
CITADEL_CONFIG_DIR = "/root/.config/citadel" if not _DEV_MODE else os.path.join(CITADEL_HOME, "system")
CITADEL_LOG_FILE   = "/var/log/citadel.log"   if not _DEV_MODE else os.path.join(CITADEL_HOME, "system", "citadel.log")
CITADEL_NOTES_DIR  = os.path.join(CITADEL_CONFIG_DIR, "notes")
CITADEL_BACKUP_DIR = os.path.join(CITADEL_CONFIG_DIR, "backups")
CITADEL_RECOVERY_DIR = os.path.join(CITADEL_CONFIG_DIR, "recovery")
CITADEL_HISTORY_FILE = os.path.join(CITADEL_CONFIG_DIR, "history.jsonl")
CITADEL_USER_CONFIG  = os.path.join(CITADEL_CONFIG_DIR, "user_config.json")


# ============================================================================
# Helpers для безопасного вызова системных утилит.
# Внутри Citadel OS (root) все бинарники — в /usr/bin/. Хардкодим пути, чтобы
# избежать PATH-инъекций и зависимости от пользовательского shell PATH.
# ============================================================================
TOOL_NMAP    = "/usr/bin/nmap"
TOOL_TSHARK  = "/usr/bin/tshark"
TOOL_AIRCRACK = "/usr/bin/aircrack-ng"
TOOL_PACMAN  = "/usr/bin/pacman"
TOOL_IP      = "/usr/bin/ip"
TOOL_SS      = "/usr/bin/ss"
TOOL_ARP     = "/usr/sbin/arp"
TOOL_PING    = "/usr/bin/ping"
TOOL_HTOP    = "/usr/bin/htop"
TOOL_EDITOR  = "/usr/bin/nano"


# Гарантируем, что runtime-директории существуют (на случай первого запуска).
for _d in (CITADEL_CONFIG_DIR, CITADEL_NOTES_DIR, CITADEL_BACKUP_DIR, CITADEL_RECOVERY_DIR):
    try:
        os.makedirs(_d, exist_ok=True)
    except OSError:
        # Если прав нет (например, dev-режим) — молча игнорируем.
        pass
