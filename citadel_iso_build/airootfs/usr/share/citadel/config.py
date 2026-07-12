# Citadel OS v3.0 - Global Configuration

VERSION = "3.0 (Modular System)"
USER_NAME = "User"
SHELL_PROMPT = "CitadelOS @ User $> "

# Пароль для входа (по умолчанию: admin)
PASSWORD_HASH = "21232f297a57a5a743894a0e4a801fc3"  # MD5 от "admin"

COLORS = {
    "PURPLE": "\033[95m",
    "CYAN": "\033[96m",
    "DARK_CYAN": "\033[36m",
    "BLUE": "\033[94m",
    "GREEN": "\033[92m",
    "YELLOW": "\033[93m",
    "RED": "\033[31m",
    "GRAY": "\033[90m",
    "RESET": "\033[0m"
}

# Текущая тема оформления (по умолчанию PURPLE)
THEME_COLOR = "PURPLE"

TEXT_DELAY = 0.002
DEBUG_MODE = False