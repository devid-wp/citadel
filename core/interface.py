import sys
import time
import os
from config import COLORS, TEXT_DELAY, VERSION, USER_NAME

def clear_screen():
    import os
    os.system('cls' if os.name == 'nt' else 'clear')

def terminal_print(text, delay=TEXT_DELAY, color_code=COLORS["GREEN"]):
    sys.stdout.write(color_code)
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write(COLORS["RESET"] + "\n")

def display_fastfetch(sys_info):
    """Вывод оригинального огромного ASCII-логотипа и характеристик системы под ним"""
    logo_path = "logo.txt"
    
    # 1. Пытаемся прочитать твой оригинальный файл logo.txt
    if os.path.exists(logo_path):
        try:
            with open(logo_path, "r", encoding="utf-8") as f:
                logo_lines = f.readlines()
            
            # Выводим логотип красивым неоновым цветом (например, CYAN или PURPLE)
            print(COLORS["CYAN"])
            for line in logo_lines:
                # Ограничиваем анимацию для огромного текста, чтобы не ждать полчаса
                sys.stdout.write(line)
            print(COLORS["RESET"])
        except Exception:
            print(f"{COLORS['RED']}[ Ошибка загрузки logo.txt ]{COLORS['RESET']}\n")
    else:
        print(f"{COLORS['YELLOW']}[ Предупреждение: Файл logo.txt не найден в папке проекта ]{COLORS['RESET']}\n")

    # 2. Аккуратная неоновая плашка с РЕАЛЬНЫМИ характеристиками ПК под логотипом
    print(f" {COLORS['PURPLE']}╔═════════════════════ СИСТЕМНАЯ СВОДКА CITADEL OS ═════════════════════╗{COLORS['RESET']}")
    print(f"  {COLORS['GREEN']} USER:{COLORS['RESET']} {USER_NAME}@citadel-core  |  {COLORS['GREEN']}OS:{COLORS['RESET']} Citadel OS v{VERSION}")
    print(f"  {COLORS['GREEN']} CPU:{COLORS['RESET']} {sys_info.get('cpu_model', 'N/A')} ")
    print(f"  {COLORS['GREEN']} RAM:{COLORS['RESET']} {sys_info.get('memory', 'N/A')}        |  {COLORS['GREEN']}UPTIME:{COLORS['RESET']} {sys_info.get('uptime', 'N/A')}")
    print(f"  {COLORS['GREEN']} HOST:{COLORS['RESET']} Win11 Environment Kernel Node")
    print(f" {COLORS['PURPLE']}╚═══════════════════════════════════════════════════════════════════════╝{COLORS['RESET']}\n")

def display_help():
    """Вывод таблицы со всеми доступными командами ОС"""
    print(f"=== {COLORS['PURPLE']}ДОСТУПНЫЕ КОМАНДЫ CITADEL OS{COLORS['RESET']} ===")
    print("-" * 65)
    commands = [
        ("fetch", "Повторный вызов системной сводки FastFetch с мега-логотипом"),
        ("netscan", "Сканирование устройств локальной сети (system/network.py)"),
        ("crypto", "Шифрование / расшифровка строк и файлов (apps/crypto.py)"),
        ("sysmon", "Мониторинг ресурсов и процессов (system/process_mgr.py)"),
        ("passgen", "Генератор устойчивых к брутфорсу паролей (apps/passgen.py)"),
        ("clear", "Очистить экран терминала"),
        ("help", "Показать эту справку по командам"),
        ("exit / q", "Безопасное завершение сессии и выход")
    ]
    for cmd, desc in commands:
        print(f"  {COLORS['CYAN']}{cmd:<12}{COLORS['RESET']} - {desc}")
    print("-" * 65 + "\n")