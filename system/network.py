import os
import sys
import subprocess
import re
import time
import config
from core.interface import clear_screen, terminal_print, display_table, get_theme_color

def scan_network():
    """Сканирование локальной сети через ARP-таблицы и быстрый Ping"""
    clear_screen()
    theme_color = get_theme_color()
    reset = config.COLORS["RESET"]
    green = config.COLORS["GREEN"]
    gray = config.COLORS["GRAY"]
    yellow = config.COLORS["YELLOW"]
    
    print(f"{theme_color}==================================================")
    print("            СЕТЕВОЙ СКАНЕР CITADEL NET-SCAN       ")
    print(f"=================================================={reset}")
    
    terminal_print("\n[ INFO ]: Инициализация сетевых интерфейсов...")
    time.sleep(0.3)
    terminal_print("[ START ]: Сбор данных из ARP-таблицы локального сегмента...\n")
    
    found_devices = []
    
    if os.name == 'nt':
        try:
            arp_output = subprocess.check_output("arp -a", shell=True).decode('cp866')
            # Регулярное выражение для извлечения IP и MAC в Windows
            ip_pattern = re.compile(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+([0-9a-fA-F-]{17})')
            found_devices = ip_pattern.findall(arp_output)
        except Exception as e:
            terminal_print(f"[ ERROR ]: Не удалось запустить arp: {e}", color_code=config.COLORS["RED"])
    else:
        # Для Linux: парсим /proc/net/arp или /usr/sbin/arp -n.
        try:
            # Пытаемся прочитать /proc/net/arp (нет внешних зависимостей)
            if os.path.exists("/proc/net/arp"):
                with open("/proc/net/arp", "r") as f:
                    lines = f.readlines()[1:] # пропускаем заголовок
                    for line in lines:
                        parts = line.split()
                        if len(parts) >= 4:
                            ip = parts[0]
                            mac = parts[3]
                            if mac != "00:00:00:00:00:00":
                                found_devices.append((ip, mac))
            else:
                arp_bin = getattr(config, "TOOL_ARP", "/usr/sbin/arp")
                arp_output = subprocess.check_output(f"{arp_bin} -n", shell=True).decode('utf-8')
                ip_pattern = re.compile(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+\S+\s+([0-9a-fA-F:]{17})')
                found_devices = ip_pattern.findall(arp_output)
        except Exception:
            try:
                # Альтернативный парсинг через /usr/bin/ip neigh show
                ip_bin = getattr(config, "TOOL_IP", "/usr/bin/ip")
                neigh_output = subprocess.check_output(f"{ip_bin} neigh show", shell=True).decode('utf-8')
                for line in neigh_output.split('\n'):
                    parts = line.split()
                    if len(parts) >= 5 and "lladdr" in parts:
                        ip = parts[0]
                        mac = parts[parts.index("lladdr") + 1]
                        found_devices.append((ip, mac))
            except Exception as e:
                terminal_print(f"[ ERROR ]: Не удалось запустить сканирование: {e}", color_code=config.COLORS["RED"])

    # Фильтруем широковещательные адреса
    valid_devices = []
    for ip, mac in found_devices:
        if ip.endswith('.255') or ip.startswith('224.') or ip.startswith('255.'):
            continue
        valid_devices.append((ip, mac))

    if not valid_devices:
        terminal_print("[ WARNING ]: Активных устройств в кэше ARP не найдено.", color_code=yellow)
    else:
        headers = ["IP-Адрес Устройства", "MAC-Адрес", "Статус"]
        rows = []
        
        for ip, mac in valid_devices:
            # Быстрый пинг для проверки статуса
            if os.name == 'nt':
                ping_cmd = f"ping -n 1 -w 100 {ip}"
            else:
                ping_cmd = f"ping -c 1 -W 1 {ip}"
                
            ping_reply = subprocess.run(ping_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            status = "ONLINE" if ping_reply.returncode == 0 else "NO REPLY / SECURE"
            rows.append([ip, mac, status])
            
        display_table(headers, rows)
        
    terminal_print("\n[ SUCCESS ]: Сетевое сканирование завершено.", color_code=green)
    input("\nНажмите Enter для продолжения...")

def ping_host():
    """Инструмент проверки связи (Ping)"""
    clear_screen()
    theme_color = get_theme_color()
    reset = config.COLORS["RESET"]
    
    print(f"{theme_color}==================================================")
    print("            СЕТЕВОЙ ПИНГЕР CITADEL PING           ")
    print(f"=================================================={reset}\n")
    
    host = input("Введите IP-адрес или домен хоста (например, 8.8.8.8): ").strip()
    if not host:
        return
        
    print(f"\nОтправка пакетов на {host}...")
    
    if os.name == 'nt':
        cmd = f"ping -n 4 {host}"
    else:
        ping_bin = getattr(config, "TOOL_PING", "/usr/bin/ping")
        cmd = f"{ping_bin} -c 4 {host}"
        
    try:
        # Запускаем пинг и стримим его вывод в реальном времени
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for line in process.stdout:
            print(line.strip())
        process.wait()
    except Exception as e:
        print(f"Ошибка при отправке ping: {e}")
        
    input("\nНажмите Enter для продолжения...")

def display_interfaces():
    """Вывод информации о сетевых интерфейсах"""
    clear_screen()
    theme_color = get_theme_color()
    reset = config.COLORS["RESET"]
    
    print(f"{theme_color}==================================================")
    print("        СЕТЕВЫЕ АДАПТЕРЫ И ИНТЕРФЕЙСЫ CITADEL     ")
    print(f"=================================================={reset}\n")
    
    if os.name == 'nt':
        # Windows: ipconfig
        try:
            output = subprocess.check_output("ipconfig", shell=True).decode('cp866')
            # Фильтруем вывод для компактности
            lines = output.split('\n')
            relevant_lines = []
            for line in lines:
                if "adapter" in line.lower() or "ipv4" in line.lower() or "subnet" in line.lower() or "gateway" in line.lower():
                    relevant_lines.append(line.strip())
            
            for line in relevant_lines:
                print(line)
        except Exception as e:
            print(f"Ошибка: {e}")
    else:
        # Linux: /usr/bin/ip -br addr (iproute2) или /usr/sbin/ifconfig (net-tools)
        try:
            ip_bin = getattr(config, "TOOL_IP", "/usr/bin/ip")
            res = subprocess.check_output(f"{ip_bin} -br addr", shell=True).decode('utf-8')
            print(res)
        except Exception:
            try:
                res = subprocess.check_output("/usr/sbin/ifconfig", shell=True).decode('utf-8')
                print(res)
            except Exception as e:
                print(f"Не удалось получить сетевые настройки: {e}")
                
    input("\nНажмите Enter для продолжения...")
