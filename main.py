import sys
import time
import os
import subprocess

from config import COLORS, VERSION, SHELL_PROMPT
from core.interface import clear_screen, terminal_print, display_fastfetch, display_help

# Список для хранения истории команд (Фича №10)
CMD_HISTORY = []

def run_linux_cmd(cmd_list):
    """Безопасный запуск реальных системных команд Linux"""
    try:
        result = subprocess.run(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
        return f"{COLORS['RED']}Ошибка системы:{COLORS['RESET']}\n{result.stderr.strip()}"
    except FileNotFoundError:
        return f"{COLORS['YELLOW']}[Системная утилита не найдена. Возможно, вы запущены не на Arch Linux]{COLORS['RESET']}"
    except Exception as e:
        return str(e)

def main():
    clear_screen()
    terminal_print("[ BOOT ]: Загрузка подсистем Citadel OS на базе Arch Linux Core...", color_code=COLORS["PURPLE"])
    time.sleep(0.4)
    
    # Собираем базовые данные
    # Интеграция с pacman (Фича №1) + ядро (Фича №2)
    pacman_pkgs = run_linux_cmd(["sh", "-c", "pacman -Q | wc -l"])
    kernel_ver = run_linux_cmd(["uname", "-r"])
    
    linux_specs = {
        "uptime": run_linux_cmd(["uptime", "-p"]) if "not found" not in run_linux_cmd(["uptime", "-p"]) else "0d 1h",
        "cpu_model": run_linux_cmd(["sh", "-c", "lscpu | grep 'Model name' | cut -d: -f2"]) if "not found" not in run_linux_cmd(["lscpu"]) else "Linux Core Processor",
        "memory": run_linux_cmd(["sh", "-c", "free -h | grep Mem | awk '{print $3 \" / \" $2}'"]) 
    }
    
    # Дописываем кастомные строки в specs для красоты
    if "not found" not in pacman_pkgs and pacman_pkgs.isdigit():
        linux_specs["memory"] += f" | Pkgs: {pacman_pkgs} (pacman)"
    
    clear_screen()
    display_fastfetch(linux_specs)
    print(f"Citadel Shell v{VERSION} успешно запущена поверх Linux Kernel {kernel_ver}.")
    print(f"Введите {COLORS['CYAN']}'help'{COLORS['RESET']} для вывода списка расширенных утилит.\n")
    
    while True:
        current_dir = os.getcwd()
        prompt = f"{COLORS['PURPLE']}[Arch@{USER_NAME} {current_dir}]$ {COLORS['RESET']}"
        
        try:
            user_input = input(prompt).strip()
        except KeyboardInterrupt:
            print("\nИспользуйте 'exit' для выхода.")
            continue
            
        if not user_input:
            continue
            
        # Запись в историю
        CMD_HISTORY.append(user_input)
        
        parts = user_input.split()
        cmd = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        
        # --- Базовые команды управления Citadel ---
        if cmd == 'help':
            display_help()
            print(f"=== {COLORS['YELLOW']}10 БАЗОВЫХ СИСТЕМНЫХ ФИЧ CITADEL OS (ARCH LINUX){COLORS['RESET']} ===")
            print(f"  {COLORS['CYAN']}sysinfo{COLORS['RESET']:<15} - [Фича 2] Показать детальные параметры Linux-ядра")
            print(f"  {COLORS['CYAN']}pkg install <p>{COLORS['RESET']:<15} - [Фича 3] Установить пакет через pacman")
            print(f"  {COLORS['CYAN']}pkg update{COLORS['RESET']:<15} - [Фича 4] Полное обновление системы Arch")
            print(f"  {COLORS['CYAN']}ps{COLORS['RESET']:<15} - [Фича 5] Список реальных процессов в системе")
            print(f"  {COLORS['CYAN']}kill <PID>{COLORS['RESET']:<15} - [Фича 6] Принудительно завершить процесс")
            print(f"  {COLORS['CYAN']}df{COLORS['RESET']:<15} - [Фича 7] Мониторинг свободного места на дисках")
            print(f"  {COLORS['CYAN']}free{COLORS['RESET']:<15} - [Фича 8] Состояние оперативной памяти и Swap")
            print(f"  {COLORS['CYAN']}ip{COLORS['RESET']:<15} - [Фича 9] Сетевые интерфейсы и IP-адреса")
            print(f"  {COLORS['CYAN']}history{COLORS['RESET']:<15} - [Фича 10] Просмотр истории команд сессии")
            print("-" * 75 + "\n")
            
        elif cmd == 'fetch':
            clear_screen()
            display_fastfetch(linux_specs)
            
        elif cmd == 'clear':
            clear_screen()
            
        elif cmd in ['exit', 'q']:
            clear_screen()
            terminal_print("Выгрузка Citadel Shell. Возврат к стандартному TTY...", color_code=COLORS["RED"])
            break
            
        # --- Реализация 10 фич ---
        elif cmd == 'sysinfo': # Фича 2
            print(f"\n--- Системная архитектура Arch ---")
            print(f"Ядро: {run_linux_cmd(['uname', '-snrmo'])}")
            print(f"Имя хоста: {run_linux_cmd(['hostname'])}")
            print()
            
        elif cmd == 'pkg': # Фичи 3 и 4
            if not args:
                print("Использование: pkg install <пакет> или pkg update\n")
                continue
            sub_cmd = args[0].lower()
            if sub_cmd == 'install':
                if len(args) < 2:
                    print("Укажите имя пакета для установки.\n")
                    continue
                print(f"Вызов менеджера пакетов Arch (требуются права root)...")
                # Запуск реальной установки через sudo pacman
                os.system(f"sudo pacman -S {args[1]}")
            elif sub_cmd == 'update':
                print("Запуск полного апгрейда репозиториев Arch Linux...")
                os.system("sudo pacman -Syu")
            print()
            
        elif cmd == 'ps': # Фича 5
            print(run_linux_cmd(["ps", "-auxf"]) if "not found" not in run_linux_cmd(["ps"]) else "Процессы недоступны.\n")
            print()
            
        elif cmd == 'kill': # Фича 6
            if not args:
                print("Укажите PID процесса.\n")
                continue
            print(run_linux_cmd(["sudo", "kill", "-9", args[0]]))
            print(f"Сигнал SIGKILL отправлен процессу {args[0]}.\n")
            
        elif cmd == 'df': # Фича 7
            print(f"\n{run_linux_cmd(['df', '-h'])}\n")
            
        elif cmd == 'free': # Фича 8
            print(f"\n{run_linux_cmd(['free', '-h'])}\n")
            
        elif cmd == 'ip': # Фича 9
            # Пытаемся вызвать современный ip route или старый ifconfig
            res = run_linux_cmd(['ip', '-br', 'addr'])
            if "[Системная утилита не найдена" in res:
                res = run_linux_cmd(['ifconfig'])
            print(f"\n{res}\n")
            
        elif cmd == 'history': # Фича 10
            print(f"\n=== ИСТОРИЯ КОМАНД СЕССИИ ===")
            for idx, h_cmd in enumerate(CMD_HISTORY, 1):
                print(f"  {idx:<4} {h_cmd}")
            print()
            
        # --- Стандартная навигация (Файловый менеджер) ---
        elif cmd == 'ls':
            try:
                files = os.listdir('.')
                for item in files:
                    if os.path.isdir(item):
                        print(f"{COLORS['BLUE']}[DIR]  {item}{COLORS['RESET']}")
                    else:
                        print(f"       {item}")
                print()
            except Exception as e:
                print(f"Ошибка: {e}\n")
                
        elif cmd == 'cd':
            target = args[0] if args else os.path.expanduser("~")
            try:
                os.chdir(target)
                print()
            except Exception as e:
                print(f"Ошибка: {e}\n")
                
        elif cmd == 'cat':
            if not args:
                print("Укажите файл.\n")
                continue
            try:
                with open(args[0], "r", encoding="utf-8", errors="ignore") as f:
                    print(f"\n--- {args[0]} ---\n{f.read()}\n----------------\n")
            except Exception as e:
                print(f"Ошибка: {e}\n")
                
        else:
            print(f"{COLORS['RED']}Отказ:{COLORS['RESET']} Команда '{cmd}' не поддерживается ядром Citadel. Введите 'help'.\n")

if __name__ == "__main__":
    main()