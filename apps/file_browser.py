import os
import shutil
import config
from core.interface import clear_screen, terminal_print, display_table, get_theme_color

def run_file_browser():
    """Интерактивный файловый браузер для консоли Citadel"""
    current_dir = os.getcwd()
    
    while True:
        clear_screen()
        theme_color = get_theme_color()
        reset = config.COLORS["RESET"]
        cyan = config.COLORS["CYAN"]
        red = config.COLORS["RED"]
        green = config.COLORS["GREEN"]
        
        print(f"{theme_color}==================================================")
        print("          ФАЙЛОВЫЙ МЕНЕДЖЕР CITADEL OS            ")
        print(f"=================================================={reset}")
        print(f"Текущая директория: {config.COLORS['BLUE']}{current_dir}{reset}\n")
        
        try:
            items = os.listdir(current_dir)
        except Exception as e:
            print(f"{red}[ ERROR ]: Не удалось прочитать директорию: {e}{reset}")
            input("\nНажмите Enter для возврата...")
            return
            
        headers = ["Имя", "Тип", "Размер (байт)"]
        rows = []
        
        # Сначала папки, потом файлы
        dirs = []
        files = []
        for item in items:
            full_path = os.path.join(current_dir, item)
            if os.path.isdir(full_path):
                dirs.append(item)
            else:
                files.append(item)
                
        dirs.sort()
        files.sort()
        
        # Добавляем переход на уровень выше
        rows.append(["..", "Папка (назад)", "-"])
        
        for d in dirs:
            rows.append([d, "Папка", "-"])
        for f in files:
            full_path = os.path.join(current_dir, f)
            try:
                size = os.path.getsize(full_path)
            except Exception:
                size = "N/A"
            rows.append([f, "Файл", str(size)])
            
        display_table(headers, rows)
        
        print("\nДоступные команды:")
        print(f"  {cyan}cd <имя>{reset}  - перейти в папку (или cd ..)")
        print(f"  {cyan}view <имя>{reset}- прочитать файл")
        print(f"  {cyan}mkdir <имя>{reset}- создать папку")
        print(f"  {cyan}rm <имя>{reset}  - удалить файл или пустую папку")
        print(f"  {cyan}b{reset}          - выход в главное меню")
        
        cmd_input = input("\nCitadel FileBrowser $> ").strip()
        if not cmd_input:
            continue
            
        parts = cmd_input.split(None, 1)
        action = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        
        if action == 'b':
            break
            
        elif action == 'cd':
            if not arg:
                continue
            if arg == '..':
                current_dir = os.path.dirname(current_dir)
            else:
                target = os.path.join(current_dir, arg)
                if os.path.isdir(target):
                    current_dir = os.path.abspath(target)
                else:
                    print(f"{red}Папка '{arg}' не найдена.{reset}")
                    time.sleep(1)
                    
        elif action == 'view':
            if not arg:
                print("Укажите имя файла.")
                time.sleep(1)
                continue
            target = os.path.join(current_dir, arg)
            if os.path.isfile(target):
                clear_screen()
                print(f"{theme_color}--- Содержимое файла: {arg} ---{reset}\n")
                try:
                    with open(target, "r", encoding="utf-8", errors="ignore") as f:
                        print(f.read())
                except Exception as e:
                    print(f"{red}Ошибка при чтении файла: {e}{reset}")
                print(f"\n{theme_color}------------------------------------{reset}")
                input("\nНажмите Enter для продолжения...")
            else:
                print(f"{red}Файл '{arg}' не найден.{reset}")
                time.sleep(1)
                
        elif action == 'mkdir':
            if not arg:
                print("Укажите имя новой папки.")
                time.sleep(1)
                continue
            target = os.path.join(current_dir, arg)
            try:
                os.makedirs(target, exist_ok=True)
                print(f"{green}Папка создана.{reset}")
            except Exception as e:
                print(f"{red}Ошибка: {e}{reset}")
            time.sleep(1)
            
        elif action == 'rm':
            if not arg:
                print("Укажите имя для удаления.")
                time.sleep(1)
                continue
            target = os.path.join(current_dir, arg)
            confirm = input(f"{red}Вы уверены, что хотите удалить '{arg}'? (y/n): {reset}").strip().lower()
            if confirm == 'y':
                try:
                    if os.path.isdir(target):
                        os.rmdir(target)
                    else:
                        os.remove(target)
                    print(f"{green}Успешно удалено.{reset}")
                except Exception as e:
                    print(f"{red}Ошибка при удалении: {e}{reset}")
                time.sleep(1)
