import os
import sys
import json
import subprocess
import config
from core.interface import clear_screen, terminal_print, display_progress_bar, display_table, get_theme_color

MOCK_DB_PATH = "system/packages_db.json"

# Базовые демо-пакеты для Windows/симуляции
DEFAULT_MOCK_REPO = {
    "fastfetch": {"version": "2.15.0", "description": "Показывает красивое инфо о системе с логотипом", "installed": False},
    "nginx": {"version": "1.24.0", "description": "Высокопроизводительный веб-сервер и прокси-сервер", "installed": False},
    "htop": {"version": "3.3.0", "description": "Интерактивный просмотрщик процессов для терминала", "installed": True},
    "git": {"version": "2.43.0", "description": "Распределенная система контроля версий", "installed": True},
    "python": {"version": "3.11.5", "description": "Язык программирования общего назначения и его рантайм", "installed": True},
    "nmap": {"version": "7.94", "description": "Сканер безопасности сети и портов", "installed": False},
    "docker": {"version": "25.0.3", "description": "Платформа для разработки, доставки и запуска контейнеров", "installed": False}
}

def load_mock_db():
    if not os.path.exists(MOCK_DB_PATH):
        save_mock_db(DEFAULT_MOCK_REPO)
        return DEFAULT_MOCK_REPO
    try:
        with open(MOCK_DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_MOCK_REPO

def save_mock_db(db):
    try:
        os.makedirs(os.path.dirname(MOCK_DB_PATH), exist_ok=True)
        with open(MOCK_DB_PATH, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=4, ensure_ascii=False)
    except Exception:
        pass

def run_package_manager(args):
    """Главный вход в Менеджер Пакетов (pkg)"""
    theme_color = get_theme_color()
    reset = config.COLORS["RESET"]
    green = config.COLORS["GREEN"]
    red = config.COLORS["RED"]
    
    if not args:
        print(f"Использование: {theme_color}pkg{reset} <команда> [аргументы]")
        print("Команды:")
        print("  install <пакет>  - Установить указанный пакет")
        print("  remove <пакет>   - Удалить указанный пакет")
        print("  search <запрос>  - Поиск пакетов в репозиториях")
        print("  list             - Показать установленные пакеты")
        print("  update           - Полное обновление системы")
        print()
        return

    sub_cmd = args[0].lower()
    
    # Режим реальной работы на Arch Linux
    is_linux = os.name != 'nt' and os.path.exists("/usr/bin/pacman")
    
    if is_linux:
        if sub_cmd == 'install':
            if len(args) < 2:
                print("Укажите имя пакета для установки.\n")
                return
            pkg_name = args[1]
            print(f"Вызов менеджера пакетов Arch (sudo pacman -S)...")
            os.system(f"sudo pacman -S {pkg_name}")
        elif sub_cmd == 'remove':
            if len(args) < 2:
                print("Укажите имя пакета для удаления.\n")
                return
            pkg_name = args[1]
            print(f"Вызов менеджера пакетов Arch (sudo pacman -R)...")
            os.system(f"sudo pacman -R {pkg_name}")
        elif sub_cmd == 'search':
            if len(args) < 2:
                print("Укажите поисковый запрос.\n")
                return
            query = args[1]
            print(f"Поиск пакета в базе pacman...")
            os.system(f"pacman -Ss {query}")
        elif sub_cmd == 'list':
            print("Установленные в системе пакеты (pacman -Q):")
            os.system("pacman -Q")
        elif sub_cmd == 'update':
            print("Запуск полного обновления Arch Linux...")
            os.system("sudo pacman -Syu")
        else:
            print(f"{red}Неизвестная команда pkg: {sub_cmd}{reset}")
    else:
        # Режим симуляции (Windows или Live-CD без pacman)
        db = load_mock_db()
        
        if sub_cmd == 'install':
            if len(args) < 2:
                print("Укажите имя пакета для установки.\n")
                return
            pkg_name = args[1].lower()
            if pkg_name not in db:
                print(f"{red}[ ERROR ]: Пакет '{pkg_name}' не найден в репозитории Citadel Store.{reset}\n")
                return
            if db[pkg_name]["installed"]:
                print(f"{green}[ INFO ]: Пакет '{pkg_name}' уже установлен в системе.{reset}\n")
                return
                
            print(f"Подготовка к установке '{pkg_name}' v{db[pkg_name]['version']}...")
            display_progress_bar(1.5, f"Загрузка и распаковка {pkg_name}")
            db[pkg_name]["installed"] = True
            save_mock_db(db)
            print(f"{green}[ SUCCESS ]: Пакет '{pkg_name}' успешно установлен.{reset}\n")
            
        elif sub_cmd == 'remove':
            if len(args) < 2:
                print("Укажите имя пакета для удаления.\n")
                return
            pkg_name = args[1].lower()
            if pkg_name not in db or not db[pkg_name]["installed"]:
                print(f"{red}[ ERROR ]: Пакет '{pkg_name}' не установлен в системе.{reset}\n")
                return
                
            print(f"Подготовка к удалению '{pkg_name}'...")
            display_progress_bar(1.0, f"Удаление файлов {pkg_name}")
            db[pkg_name]["installed"] = False
            save_mock_db(db)
            print(f"{green}[ SUCCESS ]: Пакет '{pkg_name}' успешно удален из системы.{reset}\n")
            
        elif sub_cmd == 'search':
            if len(args) < 2:
                print("Укажите поисковый запрос.\n")
                return
            query = args[1].lower()
            headers = ["Пакет", "Версия", "Статус", "Описание"]
            rows = []
            for name, info in db.items():
                if query in name or query in info["description"].lower():
                    status = "Установлен" if info["installed"] else "Доступен"
                    rows.append([name, info["version"], status, info["description"]])
            
            if not rows:
                print(f"Пакеты по запросу '{query}' не найдены.")
            else:
                display_table(headers, rows)
            print()
            
        elif sub_cmd == 'list':
            headers = ["Установленный пакет", "Версия", "Описание"]
            rows = []
            for name, info in db.items():
                if info["installed"]:
                    rows.append([name, info["version"], info["description"]])
            
            if not rows:
                print("Нет установленных пакетов.")
            else:
                display_table(headers, rows)
            print()
            
        elif sub_cmd == 'update':
            print("Синхронизация баз данных пакетов...")
            display_progress_bar(1.2, "Обновление локальных репозиториев")
            print(f"{green}[ SUCCESS ]: Все репозитории обновлены. Система готова к работе.{reset}\n")
        else:
            print(f"{red}Неизвестная команда pkg в режиме симуляции: {sub_cmd}{reset}")
            print("Доступны: install, remove, search, list, update\n")
