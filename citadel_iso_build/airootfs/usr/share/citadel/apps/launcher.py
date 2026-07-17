import os
import subprocess
import time
import config
from core.interface import clear_screen, terminal_print, get_theme_color
from core.theme_state import get_theme_state
def run_command_launcher():
    """Quick application launcher module."""
    is_win = os.name == 'nt'

    while True:
        clear_screen()
        theme_color = get_theme_color()
        reset = get_theme_state().current_palette.reset

        print(f"{theme_color}=========================================")
        print("           CITADEL COMMAND LAUNCHER      ")
        print(f"========================================={reset}")
        print("\nQuick workspace launcher:")
        print("[1] Open VS Code in the current project")

        if is_win:
            print("[2] Open Explorer (Drive D:\\citadel)")
            print("[3] Launch Browser (Google)")
            print("[4] Open Windows Task Manager")
        else:
            print("[2] Open Linux file manager")
            print("[3] Launch web browser")
            print("[4] Open system monitor (htop)")

        print("[B] Return to main menu (Back)")

        choice = input("\nSelect a program to launch: ").strip().lower()

        if choice == 'b':
            break

        try:
            if choice == '1':
                print("\n[ LAUNCH ]: Starting VS Code...")
                subprocess.Popen("code .", shell=True)
                time.sleep(1)
            elif choice == '2':
                if is_win:
                    print("\n[ LAUNCH ]: Opening folder D:\\citadel...")
                    subprocess.Popen("explorer d:\\citadel", shell=True)
                else:
                    print("\n[ LAUNCH ]: Opening file manager...")
                    # Try xdg-open
                    subprocess.Popen("xdg-open .", shell=True)
                time.sleep(1)
            elif choice == '3':
                print("\n[ LAUNCH ]: Launching web browser...")
                if is_win:
                    os.system("start https://google.com")
                else:
                    os.system("xdg-open https://google.com &")
                time.sleep(1)
            elif choice == '4':
                print("\n[ LAUNCH ]: Invoking process monitor...")
                if is_win:
                    subprocess.Popen("taskmgr", shell=True)
                else:
                    # Run /usr/bin/htop in interactive mode
                    htop = getattr(config, "TOOL_HTOP", "/usr/bin/htop")
                    os.system(htop)
                time.sleep(1)
            else:
                print("\nInvalid choice. Try again.")
                time.sleep(1)
        except Exception as e:
            print(f"\n[ ERROR ]: Failed to launch utility. Check the paths. ({e})")
            time.sleep(2)
