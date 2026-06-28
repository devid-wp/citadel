import os
import re
import time
import subprocess
import ctypes
import config
from core.interface import clear_screen, terminal_print, display_table, get_theme_color, display_progress_bar
from core.auth import change_password
from core.theme_state import get_theme_state
from system.user_config import set_user_pref, get_user_pref
from rendering.draw_utils import styled_print

def update_config_value(key, value, is_string=True):
    """Обновляет значение пользовательских настроек (user_config.json + config.py)."""
    # USER_NAME и THEME_COLOR сохраняются в user_config.json (безопаснее, чем писать в config.py).
    # PASSWORD_HASH обрабатывается в core/auth.py и не должен идти через эту функцию.
    if key in ("USER_NAME", "THEME_COLOR", "TEXT_DELAY"):
        if set_user_pref(key.lower() if key != "USER_NAME" else "user_name", value):
            # Зеркалим в config для текущей сессии (читается напрямую во многих местах).
            setattr(config, key, value)
            return True
        return False

    # Фолбэк: legacy путь — писать прямо в config.py.
    config_path = "config.py"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        new_lines = []
        replaced = False
        val_str = f'"{value}"' if is_string else str(value)

        for line in lines:
            if line.strip().startswith(f"{key} ="):
                new_lines.append(f'{key} = {val_str}\n')
                replaced = True
            else:
                new_lines.append(line)

        if not replaced:
            new_lines.append(f'\n{key} = {val_str}\n')

        with open(config_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        setattr(config, key, value)
        return True
    except Exception as e:
        print(f"Ошибка записи в config.py: {e}")
        return False

def run_security_audit():
    """Аудит безопасности системы (Security Agent)"""
    clear_screen()
    theme_color = get_theme_color()
    palette = get_theme_state().current_palette
    reset = palette.reset
    accent = palette.accent


    print(f"{theme_color}==================================================")
    print("           АУДИТ БЕЗОПАСНОСТИ CITADEL OS          ")
    print(f"=================================================={reset}\n")
    
    display_progress_bar(1.2, "Сканирование конфигураций и сетевых портов")
    
    headers = ["Параметр проверки", "Статус", "Уровень риска", "Рекомендация"]
    rows = []
    
    # 1. Проверка пароля по умолчанию
    # MD5 от admin = "21232f297a57a5a743894a0e4a801fc3"
    default_pass = getattr(config, 'PASSWORD_HASH', '') == "21232f297a57a5a743894a0e4a801fc3"
    if default_pass:
        rows.append(["Пароль администратора", "Используется дефолтный ('admin')", "КРИТИЧЕСКИЙ", "Немедленно смените пароль"])
    else:
        rows.append(["Пароль администратора", "Изменен пользователем", "НЕТ", "Регулярно обновляйте пароль"])
        
    # 2. Проверка режима отладки (Debug Mode)
    debug_mode = getattr(config, 'DEBUG_MODE', False)
    if debug_mode:
        rows.append(["Режим отладки (Debug)", "ВКЛЮЧЕН", "СРЕДНИЙ", "Отключите в продакшн-среде"])
    else:
        rows.append(["Режим отладки (Debug)", "ВЫКЛЮЧЕН", "НЕТ", "Действие не требуется"])
        
    # 3. Проверка прав root/администратора
    is_root = False
    if os.name != 'nt':
        is_root = os.getuid() == 0
    else:
        # Для Windows проверяем права администратора
        try:
            is_root = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            # Альтернативный способ через net session
            try:
                subprocess.check_call("net session", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                is_root = True
            except Exception:
                is_root = False
                
    if is_root:
        rows.append(["Права суперпользователя", "Запущено от имени Root/Admin", "НИЗКИЙ", "Используйте sudo для отдельных команд"])
    else:
        rows.append(["Права суперпользователя", "Ограниченный пользователь", "НЕТ", "Система защищена от случайных изменений"])
        
    # 4. Проверка открытых портов (быстрый аудит netstat)
    try:
        if os.name == 'nt':
            netstat = subprocess.check_output("netstat -ano", shell=True).decode('cp866')
            # Ищем прослушивание 0.0.0.0 (LISTENING)
            insecure_listeners = re.findall(r'0\.0\.0\.0:(\d+)\s+.*LISTENING', netstat)
        else:
            netstat = subprocess.check_output("ss -tlnp", shell=True).decode('utf-8')
            insecure_listeners = re.findall(r'\*|0\.0\.0\.0:(\d+)', netstat)
            
        if insecure_listeners:
            ports = ", ".join(set(insecure_listeners[:5]))
            rows.append(["Службы локальной сети", f"Открыты порты: {ports}", "СРЕДНИЙ", "Закройте ненужные службы фаерволом"])
        else:
            rows.append(["Службы локальной сети", "Внешние порты закрыты", "НЕТ", "Сетевой экран в порядке"])
    except Exception:
        rows.append(["Службы локальной сети", "Анализ портов недоступен", "НИЗКИЙ", "Проверьте сетевой фильтр вручную"])
        
    display_table(headers, rows)
    
    # Резюме
    any_high = any(r[2] in ["КРИТИЧЕСКИЙ", "ВЫСОКИЙ"] for r in rows)
    any_medium = any(r[2] == "СРЕДНИЙ" for r in rows)
    
    if any_high:
        print(f"\n{accent}[ WARNING ]: Обнаружены критические уязвимости безопасности! Примите меры.{reset}")
    elif any_medium:
        print(f"\n{accent}[ WARNING ]: Найдены предупреждения средней критичности.{reset}")
    else:
        print(f"\n{accent}[ SUCCESS ]: Аудит успешно пройден. Уязвимостей не обнаружено.{reset}")

    input("\nНажмите Enter для продолжения...")

def run_citadel_center():
    """Citadel Center - интерактивный центр управления Citadel OS"""
    while True:
        clear_screen()
        theme_color = get_theme_color()
        palette = get_theme_state().current_palette
        reset = palette.reset
        accent = palette.accent


        print(f"{theme_color}==================================================")
        print("          CITADEL CENTER - ЦЕНТР УПРАВЛЕНИЯ       ")
        print(f"=================================================={reset}")
        print(f"Пользователь: {accent}{config.USER_NAME}{reset} | Тема оформления: {theme_color}{config.THEME_COLOR}{reset}\n")

        print("[1] Изменить имя пользователя")
        print("[2] Сменить цветовую тему терминала")
        print("[3] Сменить пароль администратора")
        print("[4] Запустить аудит безопасности (Security Audit)")
        print("[B] Вернуться в главное меню (Back)")

        choice = input("\nВыберите раздел настроек: ").strip().lower()

        if choice == '1':
            clear_screen()
            new_name = input("Введите новое имя пользователя: ").strip()
            if new_name:
                if update_config_value("USER_NAME", new_name):
                    print(f"\n{accent}[ SUCCESS ]: Имя пользователя успешно изменено на '{new_name}'.{reset}")
                else:
                    print("\n[ ERROR ]: Не удалось обновить имя пользователя.")
            time.sleep(1)

        elif choice == '2':
            clear_screen()
            print("Доступные темы оформления:")
            available_themes = [k for k in config.COLORS.keys() if k != "RESET"]
            for idx, theme in enumerate(available_themes, 1):
                c = config.COLORS[theme]
                print(f"[{idx}] {c}{theme}{reset}")

            theme_choice = input("\nВыберите номер темы: ").strip()
            try:
                idx = int(theme_choice)
                if 1 <= idx <= len(available_themes):
                    selected = available_themes[idx - 1]
                    if update_config_value("THEME_COLOR", selected):
                        print(f"\n{accent}[ SUCCESS ]: Тема успешно изменена на {config.COLORS[selected]}{selected}{reset}.")
                    else:
                        print("\n[ ERROR ]: Не удалось изменить тему.")
                else:
                    print("Неверный номер.")
            except ValueError:
                print("Некорректный ввод.")
            time.sleep(1.5)

        elif choice == '3':
            clear_screen()
            print(f"{theme_color}=== СМЕНА ПАРОЛЯ АДМИНИСТРАТОРА ==={reset}\n")
            old_pass = input("Введите текущий пароль: ").strip()
            new_pass = input("Введите новый пароль: ").strip()
            confirm_pass = input("Подтвердите новый пароль: ").strip()

            if new_pass != confirm_pass:
                print(f"\n{accent}[ ERROR ]: Новые пароли не совпадают!{reset}")
            else:
                success, msg = change_password(old_pass, new_pass)
                if success:
                    print(f"\n{accent}[ SUCCESS ]: {msg}{reset}")
                else:
                    print(f"\n{accent}[ ERROR ]: {msg}{reset}")
            time.sleep(2)

        elif choice == '4':
            run_security_audit()

        elif choice == 'b':
            break
