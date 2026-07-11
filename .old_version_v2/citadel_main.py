import os
from config import COLORS, TEXT_DELAY, VERSION, USER_NAME
import sys
import time
import subprocess
import re
import random
import string

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def terminal_print(text, delay=0.003, color_code="\033[32m"):
    """Вывод текста в стиле классического терминала"""
    sys.stdout.write(color_code)
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write("\033[0m\n")

def get_local_ip_and_scan():
    """Реальное сканирование локальной сети через ARP и Ping"""
    clear_screen()
    terminal_print("==================================================", color_code="\033[94m")
    terminal_print("            LOCAL NETWORK NET-SCANNER v1.2        ", color_code="\033[94m")
    terminal_print("==================================================", color_code="\033[94m")
    
    terminal_print("\n[ INFO ]: Инициализация сетевого адаптера...")
    time.sleep(0.3)
    terminal_print("[ START ]: Сбор данных из таблицы ARP локального сегмента...\n")
    
    try:
        arp_output = subprocess.check_output("arp -a", shell=True).decode('cp866')
        ip_pattern = re.compile(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+([0-9a-fA-F-]{17})')
        found_devices = ip_pattern.findall(arp_output)
        
        if not found_devices:
            terminal_print("[ WARNING ]: Активных устройств в кэше ARP не найдено.", color_code="\033[93m")
        else:
            print(f"{'IP-Адрес Устройства':<20} | {'MAC-Адрес':<20} | {'Статус':<15}")
            print("-" * 60)
            
            for ip, mac in found_devices:
                if ip.endswith('.255') or ip.startswith('224.'):
                    continue
                    
                print(f"{ip:<20} | {mac:<20} | ", end="")
                sys.stdout.flush()
                
                ping_reply = subprocess.run(f"ping -n 1 -w 150 {ip}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                if ping_reply.returncode == 0:
                    terminal_print("ONLINE", delay=0.001, color_code="\033[92m")
                else:
                    terminal_print("NO REPLY / SECURE", delay=0.001, color_code="\033[90m")
                    
    except Exception as e:
        terminal_print(f"[ ERROR ]: Ошибка сканирования: {e}", color_code="\033[31m")

    terminal_print("\n[ SUCCESS ]: Сканирование сети завершено.", color_code="\033[92m")
    input("\nНажмите Enter для возврата в меню...")

def encrypt_decrypt_logic(text, key):
    """XOR-алгоритм для шифрования конфиденциальных файлов"""
    output = []
    for i, char in enumerate(text):
        key_char = key[i % len(key)]
        output.append(chr(ord(char) ^ ord(key_char)))
    return "".join(output)

def run_crypto_module():
    while True:
        clear_screen()
        terminal_print("=========================================", color_code="\033[36m")
        terminal_print("         SECURE CRYPTO-SHIELD SYSTEM     ", color_code="\033[36m")
        terminal_print("=========================================", color_code="\033[36m")
        print("\n[1] Зашифровать строку данных (Encrypt)")
        print("[2] Расшифровать строку данных (Decrypt)")
        print("[B] Вернуться назад (Back)")
        
        choice = input("\nВыберите опцию: ").strip().lower()
        
        if choice == '1':
            msg = input("\nВведите конфиденциальный текст: ")
            key = input("Введите ключ шифрования (пароль): ")
            coded = encrypt_decrypt_logic(msg, key)
            print("\n" + "="*40)
            print(f"ЗАШИФРОВАННЫЙ ПОТОК:\n{repr(coded)}")
            print("="*40)
            input("\nНажмите Enter для продолжения...")
        elif choice == '2':
            coded_input = input("\nВставьте зашифрованный поток (вместе с кавычками): ")
            key = input("Введите ключ расшифровки: ")
            try:
                actual_str = eval(coded_input)
                decoded = encrypt_decrypt_logic(actual_str, key)
                print("\n" + "="*40)
                terminal_print(f"РАСШИФРОВАННЫЕ ДАННЫЕ: {decoded}", color_code="\033[92m")
                print("="*40)
            except Exception as e:
                terminal_print(f"\n[ ERROR ]: Ошибка декодирования. Неверный ключ.", color_code="\033[31m")
            input("\nНажмите Enter для продолжения...")
        elif choice == 'b':
            break

def run_system_monitor():
    """Мониторинг ресурсов системы через PowerShell"""
    clear_screen()
    terminal_print("=========================================", color_code="\033[93m")
    terminal_print("         SYSTEM RESOURCE MONITOR v1.2    ", color_code="\033[93m")
    terminal_print("=========================================", color_code="\033[93m")
    print("\nСбор данных о нагрузке (нажмите Ctrl+C для выхода)...\n")
    
    try:
        while True:
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
                
                sys.stdout.write(f"\r[ HARDWARE ]: CPU Load: {cpu_load}%  |  RAM Usage: {used_mem_p}% (Свободно: {free_gb} GB / {total_gb} GB)   ")
                sys.stdout.flush()
            
            time.sleep(1.5)
            
    except KeyboardInterrupt:
        print("\n\n[ INFO ]: Мониторинг остановлен.")
        input("Нажмите Enter для продолжения...")

def run_password_generator():
    """Генератор устойчивых паролей"""
    clear_screen()
    terminal_print("=========================================", color_code="\033[96m")
    terminal_print("        SECURE PASSWORD GENERATOR        ", color_code="\033[96m")
    terminal_print("=========================================", color_code="\033[96m")
    
    try:
        length = int(input("\nВведите длину пароля (рекомендуется от 12): ").strip())
        if length < 4:
            length = 8
    except ValueError:
        length = 12
        
    include_special = input("Включать спецсимволы (!@#$%^&*)? (y/n): ").strip().lower() == 'y'
    
    chars = string.ascii_letters + string.digits
    if include_special:
        chars += "!@#$%^&*()_+-=[]{}|;:,.<>?"
        
    password = [
        random.choice(string.ascii_lowercase),
        random.choice(string.ascii_uppercase),
        random.choice(string.digits)
    ]
    if include_special:
        password.append(random.choice("!@#$%^&*()"))
        
    password += [random.choice(chars) for _ in range(length - len(password))]
    random.shuffle(password)
    final_password = "".join(password)
    
    print("\n" + "-"*40)
    terminal_print(f"СГЕНЕРИРОВАННЫЙ ПАРОЛЬ: {final_password}", color_code="\033[92m")
    print("-"*40)
    input("\nНажмите Enter для возврата в меню...")

def run_command_launcher():
    """Модуль быстрого запуска приложений и папок"""
    while True:
        clear_screen()
        terminal_print("=========================================", color_code="\033[91m") # Красный
        terminal_print("           CITADEL COMMAND LAUNCHER      ", color_code="\033[91m")
        terminal_print("=========================================", color_code="\033[91m")
        print("\nБыстрый запуск рабочей среды:")
        print("[1] Открыть VS Code в текущем проекте")
        print("[2] Открыть Проводник (Диск D:\\citadel)")
        print("[3] Запустить Браузер (По умолчанию)")
        print("[4] Открыть Диспетчер Задач Windows")
        print("[B] Вернуться в главное меню (Back)")
        
        choice = input("\nВыберите программу для запуска: ").strip().lower()
        
        try:
            if choice == '1':
                print("\n[ LAUNCH ]: Запуск VS Code...")
                # Запускает VS Code прямо в папке с проектом
                subprocess.Popen("code .", shell=True)
                time.sleep(1)
            elif choice == '2':
                print("\n[ LAUNCH ]: Открытие папки D:\\citadel...")
                # Открывает стандартный проводник Windows в нашей директории
                subprocess.Popen("explorer d:\\citadel", shell=True)
                time.sleep(1)
            elif choice == '3':
                print("\n[ LAUNCH ]: Запуск веб-браузера...")
                # Безопасно триггерит дефолтный браузер системы
                os.system("start https://google.com")
                time.sleep(1)
            elif choice == '4':
                print("\n[ LAUNCH ]: Вызов Task Manager...")
                subprocess.Popen("taskmgr", shell=True)
                time.sleep(1)
            elif choice == 'b':
                break
            else:
                print("\nНеверный выбор. Попробуйте еще раз.")
                time.sleep(1)
        except Exception as e:
            print(f"\n[ ERROR ]: Не удалось запустить утилиту. Проверьте пути. ({e})")
            time.sleep(2)

def main():
    while True:
        clear_screen()
        terminal_print("#########################################", color_code="\033[95m")
        terminal_print("         CITADEL TERMINAL CORE v2.0      ", color_code="\033[95m")
        terminal_print("         Authorized User Mode            ", color_code="\033[95m")
        terminal_print("#########################################", color_code="\033[95m")
        
        print("\n--- СИСТЕМНЫЕ МОДУЛИ ---")
        print("[1] Сканирование локальной сети   (Network Scanner)")
        print("[2] Консоль шифрования данных    (Crypto Engine)")
        print("[3] Мониторинг ресурсов системы  (System Monitor)")
        print("[4] Генератор стойких паролей    (Password Gen)")
        print("[5] Быстрый запуск приложений   (Command Launcher)")
        print("[Q] Выход из терминала           (Exit)")
        
        choice = input("\nВведите команду: ").strip().lower()
        
        if choice == '1':
            get_local_ip_and_scan()
        elif choice == '2':
            run_crypto_module()
        elif choice == '3':
            run_system_monitor()
        elif choice == '4':
            run_password_generator()
        elif choice == '5':
            run_command_launcher()
        elif choice == 'q':
            clear_screen()
            terminal_print("\nСессия завершена. Отключение терминала...\n", color_code="\033[31m")
            break
        else:
            print("\nНеизвестная команда. Повторите ввод.")
            time.sleep(1)

if __name__ == "__main__":
    main()