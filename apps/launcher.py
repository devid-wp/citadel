import os
import subprocess
import time
import config
from core.interface import clear_screen, terminal_print, get_theme_color
from core.theme_state import get_theme_state
def run_command_launcher():
    """Модуль быстрого запуска приложений"""
    is_win = os.name == 'nt'

    while True:
        clear_screen()
        theme_color = get_theme_color()
        reset = get_theme_state().current_palette.reset
        
        print(f"{theme_color}=========================================")
        print("           CITADEL COMMAND LAUNCHER      ")
        print(f"========================================={reset}")
        print("\nБыстрый запуск рабочей среды:")
        print("[1] Открыть VS Code в текущем проекте")
        
        if is_win:
            print("[2] Открыть Проводник (Диск D:\\citadel)")
            print("[3] Запустить Браузер (Google)")
            print("[4] Открыть Диспетчер Задач Windows")
        else:
            print("[2] Открыть файловый менеджер Linux")
            print("[3] Запустить веб-браузер")
            print("[4] Открыть системный монитор (htop)")
            
        print("[B] Вернуться в главное меню (Back)")
        
        choice = input("\nВыберите программу для запуска: ").strip().lower()
        
        if choice == 'b':
            break
            
        try:
            if choice == '1':
                print("\n[ LAUNCH ]: Запуск VS Code...")
                subprocess.Popen("code .", shell=True)
                time.sleep(1)
            elif choice == '2':
                if is_win:
                    print("\n[ LAUNCH ]: Открытие папки D:\\citadel...")
                    subprocess.Popen("explorer d:\\citadel", shell=True)
                else:
                    print("\n[ LAUNCH ]: Открытие файлового менеджера...")
                    # Пробуем открыть через xdg-open
                    subprocess.Popen("xdg-open .", shell=True)
                time.sleep(1)
            elif choice == '3':
                print("\n[ LAUNCH ]: Запуск веб-браузера...")
                if is_win:
                    os.system("start https://google.com")
                else:
                    os.system("xdg-open https://google.com &")
                time.sleep(1)
            elif choice == '4':
                print("\n[ LAUNCH ]: Вызов монитора процессов...")
                if is_win:
                    subprocess.Popen("taskmgr", shell=True)
                else:
                    # Запуск /usr/bin/htop в интерактивном режиме
                    htop = getattr(config, "TOOL_HTOP", "/usr/bin/htop")
                    os.system(htop)
                time.sleep(1)
            else:
                print("\nНеверный выбор. Попробуйте еще раз.")
                time.sleep(1)
        except Exception as e:
            print(f"\n[ ERROR ]: Не удалось запустить утилиту. Проверьте пути. ({e})")
            time.sleep(2)
