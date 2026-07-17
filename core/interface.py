import sys
import time
import os
import config

# Форсируем UTF-8 вывод, чтобы Unicode-рамки корректно рендерились в Windows Terminal
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def _safe_write(text):
    """Печатает строку, заменяя нераспознанные символы на '?' вместо краша"""
    try:
        print(text)
    except UnicodeEncodeError:
        # Fallback: убираем непечатаемые для данного терминала символы
        print(text.encode('ascii', errors='replace').decode('ascii'))

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def get_theme_color():
    """
    Вернуть ANSI-код «основного» цвета текущей темы окружения.

    Приоритет:
      1. ThemeState.current_palette.primary — если модуль уже инициализирован.
      2. config.THEME_COLOR (legacy) — фолбэк, чтобы функции отрисовки
         работали даже без EnvAwarenessModule (например, в тестах).

    Это ЕДИНСТВЕННАЯ точка, через которую остальной код берёт основной
    цвет. Переписывать вызовы get_theme_color() в модулях не нужно —
    достаточно запустить EnvAwarenessModule, и все они автоматически
    подхватят смену темы.
    """
    try:
        # Ленивый импорт, чтобы избежать циклических зависимостей
        # core.interface ↔ core.theme_state.
        from core.theme_state import get_theme_state
        palette = get_theme_state().current_palette
        return palette.primary
    except Exception:
        # Fallback на legacy-путь (config.THEME_COLOR).
        theme = getattr(config, 'THEME_COLOR', 'PURPLE')
        return config.COLORS.get(theme, config.COLORS["PURPLE"])

def terminal_print(text, delay=None, color_code=None):
    if delay is None:
        delay = getattr(config, 'TEXT_DELAY', 0.002)
    if color_code is None:
        color_code = get_theme_color()
        
    sys.stdout.write(color_code)
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write(config.COLORS["RESET"] + "\n")

def display_progress_bar(duration, task_name="Loading"):
    """Nice animated progress bar."""
    steps = 30
    sleep_time = duration / steps
    theme_color = get_theme_color()

    sys.stdout.write(f"{config.COLORS['GRAY']}[ INFO ]: {task_name}... {config.COLORS['RESET']}\n")
    for i in range(steps + 1):
        percent = int((i / steps) * 100)
        filled = i
        empty = steps - i
        bar = f"{theme_color}█" * filled + f"{config.COLORS['GRAY']}░" * empty
        sys.stdout.write(f"\r  {config.COLORS['CYAN']}[{bar}{config.COLORS['CYAN']}] {percent}%")
        sys.stdout.flush()
        time.sleep(sleep_time)
    sys.stdout.write(f"\n{config.COLORS['GREEN']}[ SUCCESS ]: {task_name} completed successfully!{config.COLORS['RESET']}\n\n")

def _supports_unicode():
    """Проверяет, поддерживает ли текущий терминал Unicode"""
    try:
        '┌'.encode(sys.stdout.encoding or 'ascii')
        return True
    except (UnicodeEncodeError, LookupError):
        return False

def display_table(headers, rows):
    """Отрисовка таблицы в консоли (Unicode-рамки или ASCII fallback)"""
    # Вычисляем максимальную ширину колонок
    col_widths = [len(h) for h in headers]
    for row in rows:
        for idx, val in enumerate(row):
            col_widths[idx] = max(col_widths[idx], len(str(val)))
            
    theme_color = get_theme_color()
    reset = config.COLORS["RESET"]
    
    use_unicode = _supports_unicode()
    
    if use_unicode:
        top    = theme_color + "┌" + "┬".join("─" * (w + 2) for w in col_widths) + "┐" + reset
        middle = theme_color + "├" + "┼".join("─" * (w + 2) for w in col_widths) + "┤" + reset
        bottom = theme_color + "└" + "┴".join("─" * (w + 2) for w in col_widths) + "┘" + reset
        sep = "│"
    else:
        # ASCII fallback для старых консолей (cp1251, cp866)
        top    = theme_color + "+" + "+".join("-" * (w + 2) for w in col_widths) + "+" + reset
        middle = theme_color + "+" + "+".join("-" * (w + 2) for w in col_widths) + "+" + reset
        bottom = theme_color + "+" + "+".join("-" * (w + 2) for w in col_widths) + "+" + reset
        sep = "|"
    
    _safe_write(top)
    # Заголовок
    header_str = theme_color + sep + reset + (theme_color + f" {sep} ").join(f" {h:<{col_widths[idx]}} " for idx, h in enumerate(headers)) + theme_color + f" {sep}" + reset
    _safe_write(header_str)
    _safe_write(middle)
    
    # Строки данных
    for row in rows:
        row_str = theme_color + sep + reset + f" {sep} ".join(f" {str(val):<{col_widths[idx]}} " for idx, val in enumerate(row)) + theme_color + f" {sep}" + reset
        _safe_write(row_str)
    _safe_write(bottom)

def display_fastfetch(sys_info):
    """Вывод ASCII-логотипа и характеристик системы"""
    logo_path = "logo.txt"
    theme_color = get_theme_color()
    reset = config.COLORS["RESET"]
    green = config.COLORS["GREEN"]
    purple = config.COLORS["PURPLE"]
    
    if os.path.exists(logo_path):
        try:
            with open(logo_path, "r", encoding="utf-8") as f:
                logo_lines = f.readlines()
            
            print(theme_color)
            for line in logo_lines:
                sys.stdout.write(line)
            print(reset)
        except Exception:
            print(f"{config.COLORS['RED']}[ Error loading logo.txt ]{reset}\n")
    else:
        # Резервный логотип, если logo.txt отсутствует
        print(f"{theme_color}")
        print("  ____ _ _   _   _ ____  _____ _     ")
        print(" / ___(_) |_/ |_| |  _ \\| ____| |    ")
        print("| |   | | __| __| | | | |  _| | |    ")
        print("| |___| | |_| |_| | |_| | |___| |___ ")
        print(" \\____|_|\\__|\\__|_|____/|_____|_____|")
        print(f"        CITADEL SYSTEM CORE v{getattr(config, 'CORE_VERSION', '3.0')}{reset}\n")

    user_str = f"{config.USER_NAME}@citadel-core"
    ver_str = f"Citadel OS v{config.VERSION} (Core {config.CORE_VERSION})"
    cpu_str = sys_info.get('cpu_model', 'N/A')
    ram_str = sys_info.get('memory', 'N/A')
    uptime_str = sys_info.get('uptime', 'N/A')
    host_str = "Citadel Kernel Node"
    
    print(f" {purple}╔═════════════════════ CITADEL OS SYSTEM OVERVIEW ═════════════════════╗{reset}")
    print(f"  {green} USER:{reset} {user_str:<25} |  {green}OS:{reset} {ver_str}")
    print(f"  {green} CPU:{reset} {cpu_str:<26} |  {green}HOST:{reset} {host_str}")
    print(f"  {green} RAM:{reset} {ram_str:<26} |  {green}UPTIME:{reset} {uptime_str}")
    print(f" {purple}╚═══════════════════════════════════════════════════════════════════════╝{reset}\n")

# ============================================================================
# AR-HUD module contract (добавлено для рефакторинга EnvAwarenessModule)
# ============================================================================
#
# Принцип: существующий Citadel — TUI-шелл. Мы НЕ ломаем его, а вводим
# параллельный слой "модулей HUD", который может использовать тот же слой
# отрисовки (см. rendering/draw_utils.py). IHUDModule — общий контракт
# для всех модулей HUD. EnvAwarenessModule и ClockModule реализуют его.

from abc import ABC, abstractmethod
from typing import Optional

class IHUDModule(ABC):
    """
    Базовый контракт для всех AR-HUD модулей.

    Жизненный цикл модуля:
        1. Конструктор (без побочных эффектов — не стартует фоновые потоки).
        2. start() — модуль подписывается на события, запускает воркеры.
        3. update(dt) — вызывается главным циклом HUD каждый кадр.
        4. render(surface) — модуль отрисовывает себя на канвас.
        5. stop() — корректная остановка, отписка от событий.

    Метод get_state() — для отладки и health-check.
    """

    name: str = "base"

    @abstractmethod
    def start(self) -> None:
        """Запустить модуль: подписки, потоки, таймеры."""

    @abstractmethod
    def update(self, dt: float) -> None:
        """
        Кадровый апдейт. dt — секунды с прошлого вызова.
        Тяжёлых операций здесь быть не должно.
        """

    @abstractmethod
    def render(self, surface=None) -> None:
        """
        Отрисовка модуля. Параметр surface зарезервирован для будущего
        канваса (PIL/Pygame); пока допускается None для текстового режима.
        """

    @abstractmethod
    def stop(self) -> None:
        """Остановить модуль и освободить ресурсы."""

    def get_state(self) -> dict:
        """Состояние модуля для health-check. По умолчанию — только имя."""
        return {"name": self.name, "running": True}


class ModuleRegistry:
    """
    Простой реестр активных HUD-модулей. Один инстанс на процесс (см.
    get_registry() ниже). Потокобезопасность обеспечивается внешним кодом —
    мы держим API последовательным и без блокировок внутри.
    """

    def __init__(self) -> None:
        self._modules: list[IHUDModule] = []

    def register(self, module: IHUDModule) -> None:
        if any(m.name == module.name for m in self._modules):
            raise ValueError(f"Module '{module.name}' already registered")
        self._modules.append(module)

    def start_all(self) -> None:
        for m in self._modules:
            m.start()

    def update_all(self, dt: float) -> None:
        for m in self._modules:
            m.update(dt)

    def render_all(self, surface=None) -> None:
        for m in self._modules:
            m.render(surface)

    def stop_all(self) -> None:
        for m in self._modules:
            m.stop()

    def get(self, name: str) -> Optional[IHUDModule]:
        for m in self._modules:
            if m.name == name:
                return m
        return None


_REGISTRY: Optional[ModuleRegistry] = None


def get_registry() -> ModuleRegistry:
    """Ленивая инициализация реестра модулей (синглтон на процесс)."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = ModuleRegistry()
    return _REGISTRY


def display_help():
    """Display a table of all available OS commands."""
    theme_color = get_theme_color()
    reset = config.COLORS["RESET"]
    cyan = config.COLORS["CYAN"]

    print(f"=== {theme_color}AVAILABLE CITADEL OS COMMANDS{reset} ===")
    print("-" * 75)
    commands = [
        ("fetch", "Re-run the FastFetch system overview with the logo"),
        ("center", "Citadel Center — interactive system control hub"),
        ("pkg", "Package manager (install <p>, update, search <p>, remove <p>)"),
        ("netscan", "Scan devices on the local network (Network Center)"),
        ("ip", "Show network interfaces and IP addresses"),
        ("sysmon", "Monitor CPU and RAM resources"),
        ("ps", "List active processes on the system"),
        ("kill <PID>", "Force-terminate a process by PID"),
        ("df", "Monitor disk space"),
        ("files", "Interactive file manager (navigation, viewing)"),
        ("notes", "Notes application (create, read, list)"),
        ("crypto", "Data encryption/decryption module (AES-128 + HMAC)"),
        ("passgen", "Secure password generator"),
        ("weather", "Weather: auto-detect by IP, 3-day forecast"),
        ("geo", "Detect location by IP address"),
        ("log [N]", "Last N lines of the event log"),
        ("alias ...", "Manage aliases (list/add/remove)"),
        ("lock", "Re-prompt for the password (screen lock)"),
        ("launcher", "Quick launch of developer external apps"),
        ("recovery", "Citadel backup and restore system"),
        ("history", "Show the current session's command history"),
        ("clear", "Clear the terminal screen"),
        ("help", "Show this command reference"),
        ("exit / q", "Safely end the session and quit")
    ]
    for cmd, desc in commands:
        print(f"  {cyan}{cmd:<15}{reset} - {desc}")
    print("-" * 75 + "\n")