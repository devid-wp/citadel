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

def display_progress_bar(duration, task_name="Загрузка"):
    """Красивый анимированный индикатор загрузки (Progress Bar)"""
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
    sys.stdout.write(f"\n{config.COLORS['GREEN']}[ SUCCESS ]: {task_name} завершено успешно!{config.COLORS['RESET']}\n\n")

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
            print(f"{config.COLORS['RED']}[ Ошибка загрузки logo.txt ]{reset}\n")
    else:
        # Резервный логотип, если logo.txt отсутствует
        print(f"{theme_color}")
        print("  ____ _ _   _   _ ____  _____ _     ")
        print(" / ___(_) |_/ |_| |  _ \\| ____| |    ")
        print("| |   | | __| __| | | | |  _| | |    ")
        print("| |___| | |_| |_| | |_| | |___| |___ ")
        print(" \\____|_|\\__|\\__|_|____/|_____|_____|")
        print(f"        CITADEL SYSTEM CORE v{config.VERSION}{reset}\n")

    user_str = f"{config.USER_NAME}@citadel-core"
    ver_str = f"Citadel OS v{config.VERSION}"
    cpu_str = sys_info.get('cpu_model', 'N/A')
    ram_str = sys_info.get('memory', 'N/A')
    uptime_str = sys_info.get('uptime', 'N/A')
    host_str = "Citadel Kernel Node"
    
    print(f" {purple}╔═════════════════════ СИСТЕМНАЯ СВОДКА CITADEL OS ═════════════════════╗{reset}")
    print(f"  {green} USER:{reset} {user_str:<25} |  {green}OS:{reset} {ver_str}")
    print(f"  {green} CPU:{reset} {cpu_str:<26} |  {green}HOST:{reset} {host_str}")
    print(f"  {green} RAM:{reset} {ram_str:<26} |  {green}UPTIME:{reset} {uptime_str}")
    print(f" {purple}╚═══════════════════════════════════════════════════════════════════════╝{reset}\n")

def display_help():
    """Вывод таблицы со всеми доступными командами ОС"""
    theme_color = get_theme_color()
    reset = config.COLORS["RESET"]
    cyan = config.COLORS["CYAN"]
    
    print(f"=== {theme_color}ДОСТУПНЫЕ КОМАНДЫ CITADEL OS{reset} ===")
    print("-" * 75)
    commands = [
        ("fetch", "Повторный вызов системной сводки FastFetch с логотипом"),
        ("center", "Citadel Center - интерактивный пульт управления системой"),
        ("pkg", "Управление пакетами (install <p>, update, search <p>, remove <p>)"),
        ("netscan", "Сканирование устройств локальной сети (Network Center)"),
        ("ip", "Просмотр сетевых интерфейсов и IP-адресов"),
        ("sysmon", "Мониторинг ресурсов процессора и оперативной памяти"),
        ("ps", "Список активных процессов в системе"),
        ("kill <PID>", "Принудительное завершение процесса по PID"),
        ("df", "Мониторинг дискового пространства"),
        ("files", "Интерактивный файловый менеджер (навигация, просмотр)"),
        ("notes", "Приложение для ведения заметок (создание, чтение, список)"),
        ("crypto", "Модуль шифрования/дешифрования данных (AES-128 + HMAC)"),
        ("passgen", "Генератор безопасных паролей"),
        ("weather", "Погода: авто-определение по IP, прогноз на 3 дня"),
        ("geo", "Определить местоположение по IP-адресу"),
        ("log [N]", "Последние N строк журнала событий"),
        ("alias ...", "Управление алиасами (list/add/remove)"),
        ("lock", "Повторно запросить пароль (блокировка экрана)"),
        ("launcher", "Быстрый запуск внешних приложений разработчика"),
        ("recovery", "Система резервного копирования и восстановления Citadel"),
        ("history", "Просмотр истории команд текущей сессии"),
        ("clear", "Очистить экран терминала"),
        ("help", "Показать эту справку по командам"),
        ("exit / q", "Безопасное завершение сессии и выход")
    ]
    for cmd, desc in commands:
        print(f"  {cyan}{cmd:<15}{reset} - {desc}")
    print("-" * 75 + "\n")