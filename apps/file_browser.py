import os
import shutil
import config
from core.interface import clear_screen, terminal_print, display_table, get_theme_color
from core.theme_state import get_theme_state
from rendering.draw_utils import styled_print

def run_file_browser():
    """Interactive file browser for the Citadel console."""
    current_dir = os.getcwd()

    while True:
        clear_screen()
        theme_color = get_theme_color()
        palette = get_theme_state().current_palette
        reset = palette.reset
        accent = palette.accent  # in DAY/EVENING=YELLOW, in NIGHT=RED


        print(f"{theme_color}==================================================")
        print("          CITADEL OS FILE MANAGER                ")
        print(f"=================================================={reset}")
        print(f"Current directory: {accent}{current_dir}{reset}\n")

        try:
            items = os.listdir(current_dir)
        except Exception as e:
            print(f"{accent}[ ERROR ]: Failed to read directory: {e}{reset}")
            input("\nPress Enter to return...")
            return

        headers = ["Name", "Type", "Size (bytes)"]
        rows = []

        # Folders first, then files
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

        # Add a "go up one level" entry
        rows.append(["..", "Folder (up)", "-"])

        for d in dirs:
            rows.append([d, "Folder", "-"])
        for f in files:
            full_path = os.path.join(current_dir, f)
            try:
                size = os.path.getsize(full_path)
            except Exception:
                size = "N/A"
            rows.append([f, "File", str(size)])

        display_table(headers, rows)

        print("\nAvailable commands:")
        print(f"  {accent}cd <name>{reset}  - enter a folder (or cd ..)")
        print(f"  {accent}view <name>{reset} - read a file")
        print(f"  {accent}mkdir <name>{reset} - create a folder")
        print(f"  {accent}rm <name>{reset}  - delete a file or empty folder")
        print(f"  {accent}b{reset}           - return to main menu")

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
                    print(f"{accent}Folder '{arg}' not found.{reset}")
                    time.sleep(1)

        elif action == 'view':
            if not arg:
                print("Specify a file name.")
                time.sleep(1)
                continue
            target = os.path.join(current_dir, arg)
            if os.path.isfile(target):
                clear_screen()
                print(f"{theme_color}--- Contents of file: {arg} ---{reset}\n")
                try:
                    with open(target, "r", encoding="utf-8", errors="ignore") as f:
                        print(f.read())
                except Exception as e:
                    print(f"{accent}Error reading file: {e}{reset}")
                print(f"\n{theme_color}------------------------------------{reset}")
                input("\nPress Enter to continue...")
            else:
                print(f"{accent}File '{arg}' not found.{reset}")
                time.sleep(1)

        elif action == 'mkdir':
            if not arg:
                print("Specify a name for the new folder.")
                time.sleep(1)
                continue
            target = os.path.join(current_dir, arg)
            try:
                os.makedirs(target, exist_ok=True)
                print(f"{accent}Folder created.{reset}")
            except Exception as e:
                print(f"{accent}Error: {e}{reset}")
            time.sleep(1)

        elif action == 'rm':
            if not arg:
                print("Specify a name to delete.")
                time.sleep(1)
                continue
            target = os.path.join(current_dir, arg)
            confirm = input(f"{accent}Are you sure you want to delete '{arg}'? (y/n): {reset}").strip().lower()
            if confirm == 'y':
                try:
                    if os.path.isdir(target):
                        os.rmdir(target)
                    else:
                        os.remove(target)
                    print(f"{accent}Deleted successfully.{reset}")
                except Exception as e:
                    print(f"{accent}Delete error: {e}{reset}")
                time.sleep(1)
