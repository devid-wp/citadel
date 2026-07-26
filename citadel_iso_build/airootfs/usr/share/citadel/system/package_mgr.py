import os
import sys
import json
import subprocess
import config
from core.interface import clear_screen, terminal_print, display_progress_bar, display_table, get_theme_color

# Mock-DB. В production — /root/.config/citadel/packages_db.json, в dev — system/packages_db.json.
MOCK_DB_PATH = os.path.join(
    getattr(config, "CITADEL_CONFIG_DIR", "system"),
    "packages_db.json",
)

# Базовые демо-пакеты для Windows/симуляции
DEFAULT_MOCK_REPO = {
    "fastfetch": {"version": "2.15.0", "description": "Displays beautiful system info with logo", "installed": False},
    "nginx": {"version": "1.24.0", "description": "High-performance web server and reverse proxy", "installed": False},
    "htop": {"version": "3.3.0", "description": "Interactive process viewer for terminal", "installed": True},
    "git": {"version": "2.43.0", "description": "Distributed version control system", "installed": True},
    "python": {"version": "3.11.5", "description": "General-purpose programming language and its runtime", "installed": True},
    "nmap": {"version": "7.94", "description": "Network security and port scanner", "installed": False},
    "docker": {"version": "25.0.3", "description": "Platform for building, shipping, and running containers", "installed": False}
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
    """Main entry to the Package Manager (pkg)."""
    theme_color = get_theme_color()
    reset = config.COLORS["RESET"]
    green = config.COLORS["GREEN"]
    red = config.COLORS["RED"]
    
    if not args:
        print(f"Usage: {theme_color}pkg{reset} <command> [arguments]")
        print("Commands:")
        print("  install <package>  - Install the specified package")
        print("  remove <package>   - Remove the specified package")
        print("  search <query>     - Search packages in repositories")
        print("  list               - Show installed packages")
        print("  update             - Full system update")
        print()
        return

    sub_cmd = args[0].lower()

    # Real-Arch mode
    is_linux = os.name != 'nt' and os.path.exists("/usr/bin/pacman")
    pacman = getattr(config, "TOOL_PACMAN", "/usr/bin/pacman")

    if is_linux:
        if sub_cmd == 'install':
            if len(args) < 2:
                print("Specify the package name to install.\n")
                return
            pkg_name = args[1]
            print(f"Calling Arch package manager (sudo {pacman} -S)...")
            os.system(f"sudo {pacman} -S {pkg_name}")
        elif sub_cmd == 'remove':
            if len(args) < 2:
                print("Specify the package name to remove.\n")
                return
            pkg_name = args[1]
            print(f"Calling Arch package manager (sudo {pacman} -R)...")
            os.system(f"sudo {pacman} -R {pkg_name}")
        elif sub_cmd == 'search':
            if len(args) < 2:
                print("Specify a search query.\n")
                return
            query = args[1]
            print(f"Searching package in pacman database...")
            os.system(f"{pacman} -Ss {query}")
        elif sub_cmd == 'list':
            print(f"Packages installed on the system ({pacman} -Q):")
            os.system(f"{pacman} -Q")
        elif sub_cmd == 'update':
            print("Starting full Arch Linux update...")
            os.system(f"sudo {pacman} -Syu")
        else:
            print(f"{red}Unknown pkg command: {sub_cmd}{reset}")
    else:
        # Simulation mode (Windows or Live-CD without pacman)
        db = load_mock_db()

        if sub_cmd == 'install':
            if len(args) < 2:
                print("Specify the package name to install.\n")
                return
            pkg_name = args[1].lower()
            if pkg_name not in db:
                print(f"{red}[ ERROR ]: Package '{pkg_name}' not found in the Citadel Store repository.{reset}\n")
                return
            if db[pkg_name]["installed"]:
                print(f"{green}[ INFO ]: Package '{pkg_name}' is already installed on the system.{reset}\n")
                return

            print(f"Preparing to install '{pkg_name}' v{db[pkg_name]['version']}...")
            display_progress_bar(1.5, f"Downloading and unpacking {pkg_name}")
            db[pkg_name]["installed"] = True
            save_mock_db(db)
            print(f"{green}[ SUCCESS ]: Package '{pkg_name}' installed successfully.{reset}\n")

        elif sub_cmd == 'remove':
            if len(args) < 2:
                print("Specify the package name to remove.\n")
                return
            pkg_name = args[1].lower()
            if pkg_name not in db or not db[pkg_name]["installed"]:
                print(f"{red}[ ERROR ]: Package '{pkg_name}' is not installed on the system.{reset}\n")
                return

            print(f"Preparing to remove '{pkg_name}'...")
            display_progress_bar(1.0, f"Removing files of {pkg_name}")
            db[pkg_name]["installed"] = False
            save_mock_db(db)
            print(f"{green}[ SUCCESS ]: Package '{pkg_name}' successfully removed from the system.{reset}\n")

        elif sub_cmd == 'search':
            if len(args) < 2:
                print("Specify a search query.\n")
                return
            query = args[1].lower()
            headers = ["Package", "Version", "Status", "Description"]
            rows = []
            for name, info in db.items():
                if query in name or query in info["description"].lower():
                    status = "Installed" if info["installed"] else "Available"
                    rows.append([name, info["version"], status, info["description"]])

            if not rows:
                print(f"No packages found for query '{query}'.")
            else:
                display_table(headers, rows)
            print()

        elif sub_cmd == 'list':
            headers = ["Installed package", "Version", "Description"]
            rows = []
            for name, info in db.items():
                if info["installed"]:
                    rows.append([name, info["version"], info["description"]])

            if not rows:
                print("No installed packages.")
            else:
                display_table(headers, rows)
            print()

        elif sub_cmd == 'update':
            print("Synchronizing package databases...")
            display_progress_bar(1.2, "Updating local repositories")
            print(f"{green}[ SUCCESS ]: All repositories updated. The system is ready for use.{reset}\n")
        else:
            print(f"{red}Unknown pkg command in simulation mode: {sub_cmd}{reset}")
            print("Available: install, remove, search, list, update\n")
