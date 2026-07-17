# Citadel OS v1.0 — Global Configuration
#
# Source of truth for all system versions:
#   VERSION       — public release version (display only).
#   CORE_VERSION  — internal engine version (shell + recovery + history).
# All modules should read both constants from here instead of hardcoding.

VERSION = "1.0"
CORE_VERSION = "3.0"

USER_NAME = "User"
SHELL_PROMPT = "CitadelOS @ User $> "

# Login password (default: admin)
# MD5("admin") is kept as a legacy fallback for already-generated rootfs.
# On first login the user must change it (see core/auth.py).
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

# Current theme (default PURPLE)
THEME_COLOR = "PURPLE"

TEXT_DELAY = 0.002
DEBUG_MODE = False


# ============================================================================
# Runtime paths. All absolute paths are for the /opt/citadel/ rootfs.
# In dev mode (on the host) they are replaced with repo-local paths via _resolve_*.
# ============================================================================
import os
import sys

_DEV_MODE = os.environ.get("CITADEL_DEV") == "1" or not os.path.isdir("/opt/citadel")

def _resolve(opt_path: str, dev_path: str) -> str:
    """If /opt/citadel exists and not in dev mode — opt_path, otherwise dev_path."""
    if _DEV_MODE:
        return dev_path
    return opt_path if os.path.isabs(opt_path) else os.path.join("/opt/citadel", opt_path.lstrip("/"))


# Base Citadel directory. In production — /opt/citadel/, in dev — repo root.
CITADEL_HOME = "/opt/citadel" if not _DEV_MODE else os.path.dirname(os.path.abspath(__file__))

# Configs and runtime state (logs, recovery snapshots, history, notes).
CITADEL_CONFIG_DIR = "/root/.config/citadel" if not _DEV_MODE else os.path.join(CITADEL_HOME, "system")
CITADEL_LOG_FILE   = "/var/log/citadel.log"   if not _DEV_MODE else os.path.join(CITADEL_HOME, "system", "citadel.log")
CITADEL_NOTES_DIR  = os.path.join(CITADEL_CONFIG_DIR, "notes")
CITADEL_BACKUP_DIR = os.path.join(CITADEL_CONFIG_DIR, "backups")
CITADEL_RECOVERY_DIR = os.path.join(CITADEL_CONFIG_DIR, "recovery")
CITADEL_HISTORY_FILE = os.path.join(CITADEL_CONFIG_DIR, "history.jsonl")
CITADEL_USER_CONFIG  = os.path.join(CITADEL_CONFIG_DIR, "user_config.json")


# ============================================================================
# Helpers for safely invoking system utilities.
# Inside Citadel OS (root) all binaries live in /usr/bin/. We hardcode paths
# to avoid PATH injection and to remove the dependency on the user shell PATH.
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


# Make sure runtime directories exist (in case of first run).
for _d in (CITADEL_CONFIG_DIR, CITADEL_NOTES_DIR, CITADEL_BACKUP_DIR, CITADEL_RECOVERY_DIR):
    try:
        os.makedirs(_d, exist_ok=True)
    except OSError:
        # If we lack permissions (e.g. in dev mode) — silently ignore.
        pass
