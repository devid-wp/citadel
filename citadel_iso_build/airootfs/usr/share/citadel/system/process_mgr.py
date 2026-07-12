import os
import sys
import subprocess
import time
import config
from core.interface import clear_screen, terminal_print, display_table

def get_process_list():
    """Возвращает список запущенных процессов для вывода в таблицу"""
    headers = ["PID", "Имя процесса", "Имя пользователя / Сессия"]
    rows = []
    
    if os.name == 'nt':
        try:
            # Получаем процессы через tasklist
            output = subprocess.check_output("tasklist /FO CSV /NH", shell=True).decode('cp866')
            lines = output.strip().split('\n')
            for line in lines:
                if not line.strip():
                    continue
                parts = [p.strip('"') for p in line.split('",')]
                if len(parts) >= 3:
                    # Имя, PID, Сессия
                    rows.append([parts[1], parts[0], parts[2]])
        except Exception as e:
            rows.append(["0", "Ошибка получения списка", str(e)])
    else:
        try:
            # Получаем процессы через ps
            output = subprocess.check_output(["ps", "-eo", "pid,comm,user", "--no-headers"]).decode('utf-8')
            lines = output.strip().split('\n')
            for line in lines:
                parts = line.strip().split(None, 2)
                if len(parts) >= 3:
                    rows.append([parts[0], parts[1], parts[2]])
                elif len(parts) == 2:
                    rows.append([parts[0], parts[1], "root"])
        except Exception as e:
            rows.append(["0", "Ошибка получения списка", str(e)])
            
    # Ограничиваем список первыми 40 процессами, чтобы не перегружать экран
    return headers, rows[:40]

def kill_process(pid):
    """Безопасное завершение процесса по PID"""
    if not pid.isdigit():
        return False, "Неверный формат PID"
        
    if os.name == 'nt':
        cmd = f"taskkill /F /PID {pid}"
    else:
        cmd = f"sudo kill -9 {pid}"
        
    try:
        result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            return True, f"Процесс {pid} успешно завершен."
        else:
            return False, result.stderr.strip()
    except Exception as e:
        return False, str(e)

def run_system_monitor():
    """Мониторинг ресурсов процессора и оперативной памяти в реальном времени"""
    clear_screen()
    theme_color = config.COLORS.get(getattr(config, 'THEME_COLOR', 'PURPLE'), config.COLORS["PURPLE"])
    reset = config.COLORS["RESET"]
    
    print(f"{theme_color}==================================================")
    print("         МОНИТОРИНГ РЕСУРСОВ CITADEL v3.0         ")
    print(f"=================================================={reset}")
    print("\nСбор данных о нагрузке (нажмите Ctrl+C для выхода)...\n")
    
    try:
        while True:
            if os.name == 'nt':
                # Сбор данных под Windows через PowerShell
                ps_cmd = (
                    "powershell -command \""
                    "$cpu = (Get-CimInstance Win32_Processor).LoadPercentage; "
                    "$os = Get-CimInstance Win32_OperatingSystem; "
                    "$total = $os.TotalVisibleMemorySize; "
                    "$free = $os.FreePhysicalMemory; "
                    "\\\"$cpu|$total|$free\\\"\""
                )
                output = subprocess.check_output(ps_cmd, shell=True).decode('cp866').strip()
                if "|" in output:
                    cpu, total, free = output.split("|")
                    cpu_load = cpu.strip()
                    total_mem = int(total.strip())
                    free_mem = int(free.strip())
                    used_mem = total_mem - free_mem
                    used_mem_p = round((used_mem / total_mem) * 100, 1)
                    free_gb = round(free_mem / 1024 / 1024, 2)
                    total_gb = round(total_mem / 1024 / 1024, 2)
                    sys.stdout.write(f"\r[ HARDWARE ]: CPU: {cpu_load}% | RAM: {used_mem_p}% (Свободно: {free_gb} GB / {total_gb} GB)   ")
                    sys.stdout.flush()
            else:
                # Сбор данных под Linux
                # 1. CPU
                try:
                    cpu_out = subprocess.check_output("top -b -n 1 | grep '%Cpu(s)'", shell=True).decode('utf-8')
                    # Извлекаем idle cpu
                    match = re.search(r'(\d+[\.,]\d+)\s+id', cpu_out)
                    if match:
                        idle = float(match.group(1).replace(',', '.'))
                        cpu_load = round(100.0 - idle, 1)
                    else:
                        cpu_load = "N/A"
                except Exception:
                    cpu_load = "N/A"
                    
                # 2. RAM
                try:
                    mem_out = subprocess.check_output("free -m", shell=True).decode('utf-8').split('\n')
                    # Строка Mem: total used free shared buff/cache available
                    mem_line = [line for line in mem_out if "Mem:" in line][0].split()
                    total_mem = int(mem_line[1])
                    used_mem = int(mem_line[2])
                    used_mem_p = round((used_mem / total_mem) * 100, 1)
                    free_gb = round((total_mem - used_mem) / 1024, 2)
                    total_gb = round(total_mem / 1024, 2)
                except Exception:
                    used_mem_p = "N/A"
                    free_gb = "N/A"
                    total_gb = "N/A"
                    
                sys.stdout.write(f"\r[ HARDWARE ]: CPU: {cpu_load}% | RAM: {used_mem_p}% (Свободно: {free_gb} GB / {total_gb} GB)   ")
                sys.stdout.flush()
                
            time.sleep(1.5)
            
    except KeyboardInterrupt:
        print(f"\n\n{config.COLORS['GRAY']}[ INFO ]: Мониторинг остановлен.{reset}")
        input("Нажмите Enter для возврата...")
