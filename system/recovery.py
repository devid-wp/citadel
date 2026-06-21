import os
import shutil
import time
import glob
import config
from core.interface import clear_screen, terminal_print, display_table, get_theme_color, display_progress_bar

BACKUP_DIR = "system/backups"

def create_backup():
    """Создает резервную копию конфигурации config.py"""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"config_backup_{timestamp}.py")

    try:
        shutil.copy("config.py", backup_file)
        return True, backup_file
    except Exception as e:
        return False, str(e)

def get_backups():
    """Возвращает список существующих резервных копий"""
    if not os.path.exists(BACKUP_DIR):
        return []
    files = glob.glob(os.path.join(BACKUP_DIR, "config_backup_*.py"))
    # Сортируем по времени изменения от новых к старым
    files.sort(key=os.path.getmtime, reverse=True)
    return files

def restore_backup(backup_path):
    """Восстанавливает config.py из бэкапа"""
    if not os.path.exists(backup_path):
        return False, "Файл бэкапа не найден"
    try:
        shutil.copy(backup_path, "config.py")
        return True, "Файл конфигурации восстановлен. Перезагрузите терминал для применения изменений."
    except Exception as e:
        return False, str(e)

def check_system_integrity():
    """Проверяет целостность критических файлов системы Citadel"""
    critical_files = [
        "main.py",
        "config.py",
        "core/interface.py",
        "core/auth.py",
        "core/shell_utils.py",
        "system/hardware.py",
        "system/process_mgr.py",
        "system/network.py",
        "system/package_mgr.py",
        "system/recovery.py",
        "system/geo.py",
        "system/user_config.py",
        "system/logger.py",
        "apps/crypto.py",
        "apps/passgen.py",
        "apps/file_browser.py",
        "apps/notes.py",
        "apps/launcher.py",
        "apps/weather.py",
    ]

    headers = ["Файл", "Статус", "Размер", "Рекомендация"]
    rows = []

    for filepath in critical_files:
        if not os.path.exists(filepath):
            rows.append([filepath, "ОТСУТСТВУЕТ", "0 байт", "Пересоздать / восстановить"])
        else:
            size = os.path.getsize(filepath)
            if size == 0:
                rows.append([filepath, "ПУСТОЙ / ПОВРЕЖДЕН", f"{size} байт", "Перезаписать рабочий код"])
            else:
                rows.append([filepath, "ОК", f"{size} байт", "Действие не требуется"])

    return headers, rows

def run_recovery_menu():
    """Интерактивное меню системы восстановления"""
    while True:
        clear_screen()
        theme_color = get_theme_color()
        reset = config.COLORS["RESET"]
        green = config.COLORS["GREEN"]
        red = config.COLORS["RED"]

        print(f"{theme_color}==================================================")
        print("          СИСТЕМА ВОССТАНОВЛЕНИЯ CITADEL          ")
        print(f"=================================================={reset}")
        print("\nВыберите действие:")
        print("[1] Проверить целостность файлов системы")
        print("[2] Создать резервную копию конфигурации (config.py)")
        print("[3] Восстановить конфигурацию из резервной копии")
        print("[B] Вернуться назад (Back)")

        choice = input("\nВведите пункт меню: ").strip().lower()

        if choice == '1':
            clear_screen()
            print(f"{theme_color}--- Проверка целостности компонентов системы ---{reset}\n")
            headers, rows = check_system_integrity()
            display_table(headers, rows)

            any_corrupt = any(r[1] != "ОК" for r in rows)
            if any_corrupt:
                print(f"\n{red}[ WARNING ]: Обнаружены поврежденные или отсутствующие компоненты!{reset}")
            else:
                print(f"\n{green}[ SUCCESS ]: Все критические файлы целостны.{reset}")

            input("\nНажмите Enter для продолжения...")

        elif choice == '2':
            clear_screen()
            print("Создание точки восстановления...")
            display_progress_bar(1.0, "Резервное копирование")
            success, path = create_backup()
            if success:
                print(f"{green}[ SUCCESS ]: Бэкап успешно создан: {os.path.basename(path)}{reset}")
            else:
                print(f"{red}[ ERROR ]: Ошибка создания бэкапа: {path}{reset}")
            input("\nНажмите Enter для продолжения...")

        elif choice == '3':
            clear_screen()
            backups = get_backups()
            if not backups:
                print("Резервные копии не найдены.")
                input("\nНажмите Enter для продолжения...")
                continue

            print(f"{theme_color}Доступные точки восстановления:{reset}\n")
            for idx, path in enumerate(backups, 1):
                mtime = time.ctime(os.path.getmtime(path))
                print(f"[{idx}] {os.path.basename(path)} (Создан: {mtime})")

            select = input("\nВыберите номер бэкапа для восстановления или 'b' для отмены: ").strip()
            if select.lower() == 'b':
                continue

            try:
                num = int(select)
                if 1 <= num <= len(backups):
                    target = backups[num - 1]
                    display_progress_bar(1.2, "Восстановление конфигурации")
                    success, msg = restore_backup(target)
                    if success:
                        print(f"{green}[ SUCCESS ]: {msg}{reset}")
                    else:
                        print(f"{red}[ ERROR ]: {msg}{reset}")
                else:
                    print("Неверный номер.")
            except ValueError:
                print("Некорректный ввод.")
            input("\nНажмите Enter для продолжения...")

        elif choice == 'b':
            break