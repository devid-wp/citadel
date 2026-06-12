import sys
import time
import os
import subprocess
import config
from core.interface import clear_screen, terminal_print, display_fastfetch, display_help, display_table
from core.auth import login_screen
from system.hardware import get_system_specs
from system.process_mgr import get_process_list, kill_process, run_system_monitor
from system.network import scan_network, ping_host, display_interfaces
from system.package_mgr import run_package_manager
from system.recovery import run_recovery_menu
from apps.crypto import run_crypto_module
from apps.passgen import run_passgen
from apps.file_browser import run_file_browser
from apps.notes import run_notes_app
from apps.launcher import run_command_launcher
from apps.center import run_citadel_center

# Список для хранения истории команд
CMD_HISTORY = []

def run_linux_cmd(cmd_list):
    """Безопасный запуск системных команд"""
    try:
        result = subprocess.run(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
        return f"{config.COLORS['RED']}Ошибка системы:{config.COLORS['RESET']}\n{result.stderr.strip()}"
    except FileNotFoundError:
        return f"{config.COLORS['YELLOW']}[Системная утилита не найдена]{config.COLORS['RESET']}"
    except Exception as e:
        return str(e)

def run_df():
    """Мониторинг свободного места на дисках (кроссплатформенный)"""
    theme_color = config.COLORS.get(getattr(config, 'THEME_COLOR', 'PURPLE'), config.COLORS["PURPLE"])
    reset = config.COLORS["RESET"]
    
    print(f"\n{theme_color}--- Мониторинг дискового пространства ---{reset}")
    if os.name == 'nt':
        try:
            # Вызов PowerShell для получения дисков
            ps_cmd = "powershell -command \"Get-Volume | Select-Object DriveLetter, FileSystemType, @{Name='SizeGB';Expression={[math]::round($_.Size/1GB,2)}}, @{Name='FreeGB';Expression={[math]::round($_.SizeRemaining/1GB,2)}} | Format-Table -HideTableHeaders\""
            output = subprocess.check_output(ps_cmd, shell=True).decode('cp866').strip()
            
            headers = ["Диск", "ФС", "Размер", "Свободно"]
            rows = []
            for line in output.split('\n'):
                parts = line.split()
                if len(parts) >= 3:
                    # Диск может быть пустым
                    if len(parts) == 3:
                        rows.append(["N/A", parts[0], f"{parts[1]} GB", f"{parts[2]} GB"])
                    else:
                        rows.append([f"{parts[0]}:", parts[1], f"{parts[2]} GB", f"{parts[3]} GB"])
            display_table(headers, rows)
        except Exception as e:
            print(f"Ошибка PowerShell: {e}")
    else:
        print(run_linux_cmd(['df', '-h']))
    print()

def run_free():
    """Состояние оперативной памяти (кроссплатформенный)"""
    theme_color = config.COLORS.get(getattr(config, 'THEME_COLOR', 'PURPLE'), config.COLORS["PURPLE"])
    reset = config.COLORS["RESET"]
    
    print(f"\n{theme_color}--- Мониторинг оперативной памяти ---{reset}")
    if os.name == 'nt':
        try:
            ps_cmd = "powershell -command \"$os = Get-CimInstance Win32_OperatingSystem; $total = [math]::round($os.TotalVisibleMemorySize/1024/1024,2); $free = [math]::round($os.FreePhysicalMemory/1024/1024,2); \\\"$total|$free\\\"\""
            output = subprocess.check_output(ps_cmd, shell=True).decode('cp866').strip()
            if "|" in output:
                total, free = output.split("|")
                headers = ["Параметр", "Объем памяти (GB)"]
                rows = [
                    ["Всего памяти", total],
                    ["Свободно памяти", free],
                    ["Использовано", str(round(float(total) - float(free), 2))]
                ]
                display_table(headers, rows)
        except Exception as e:
            print(f"Ошибка PowerShell: {e}")
    else:
        print(run_linux_cmd(['free', '-h']))
    print()

def main():
    # Шаг 1: Авторизация
    login_screen()
    
    # Загружаем характеристики
    specs = get_system_specs()
    
    clear_screen()
    display_fastfetch(specs)
    
    theme_color = config.COLORS.get(getattr(config, 'THEME_COLOR', 'PURPLE'), config.COLORS["PURPLE"])
    reset = config.COLORS["RESET"]
    cyan = config.COLORS["CYAN"]
    purple = config.COLORS["PURPLE"]
    red = config.COLORS["RED"]
    
    print(f"Citadel Shell v{config.VERSION} успешно запущена поверх {sys.platform.capitalize()} Kernel.")
    print(f"Введите {cyan}'help'{reset} для вывода списка расширенных утилит.\n")
    
    while True:
        current_dir = os.getcwd()
        user_name = getattr(config, 'USER_NAME', 'User')
        prompt = f"{purple}[Citadel@{user_name} {os.path.basename(current_dir)}]$ {reset}"
        
        try:
            user_input = input(prompt).strip()
        except KeyboardInterrupt:
            print("\nИспользуйте 'exit' или 'q' для выхода.")
            continue
        except EOFError:
            break
            
        if not user_input:
            continue
            
        # Запись в историю
        CMD_HISTORY.append(user_input)
        
        parts = user_input.split()
        cmd = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        
        # --- Базовые команды Citadel ---
        if cmd == 'help':
            display_help()
            
        elif cmd == 'fetch':
            clear_screen()
            display_fastfetch(get_system_specs())
            
        elif cmd == 'clear':
            clear_screen()
            
        elif cmd in ['exit', 'q']:
            clear_screen()
            terminal_print("Выгрузка Citadel Shell. Отключение терминала...", color_code=config.COLORS["RED"])
            break
            
        # --- Системные команды ---
        elif cmd == 'center':
            run_citadel_center()
            
        elif cmd == 'pkg':
            run_package_manager(args)
            
        elif cmd == 'netscan':
            scan_network()
            
        elif cmd == 'ping':
            ping_host()
            
        elif cmd == 'ip':
            display_interfaces()
            
        elif cmd == 'sysmon':
            run_system_monitor()
            
        elif cmd == 'ps':
            headers, rows = get_process_list()
            display_table(headers, rows)
            print()
            
        elif cmd == 'kill':
            if not args:
                print("Укажите PID процесса.\n")
                continue
            success, msg = kill_process(args[0])
            if success:
                print(f"{config.COLORS['GREEN']}[ SUCCESS ]: {msg}{reset}\n")
            else:
                print(f"{red}[ ERROR ]: {msg}{reset}\n")
                
        elif cmd == 'df':
            run_df()
            
        elif cmd == 'free':
            run_free()
            
        elif cmd == 'files':
            run_file_browser()
            
        elif cmd == 'notes':
            run_notes_app()
            
        elif cmd == 'crypto':
            run_crypto_module()
            
        elif cmd == 'passgen':
            run_passgen()
            
        elif cmd == 'launcher':
            run_command_launcher()
            
        elif cmd == 'recovery':
            run_recovery_menu()
            
        elif cmd == 'history':
            print(f"\n=== ИСТОРИЯ КОМАНД СЕССИИ ===")
            for idx, h_cmd in enumerate(CMD_HISTORY, 1):
                print(f"  {idx:<4} {h_cmd}")
            print()
            
        # --- Стандартная навигация (Файловый менеджер) ---
        elif cmd == 'ls':
            try:
                files = os.listdir('.')
                for item in files:
                    full_path = os.path.join('.', item)
                    if os.path.isdir(full_path):
                        print(f"{config.COLORS['BLUE']}[DIR]  {item}{reset}")
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
            print(f"{red}Отказ:{reset} Команда '{cmd}' не поддерживается ядром Citadel. Введите 'help'.\n")

if __name__ == "__main__":
    main()