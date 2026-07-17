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

    # Фолбэк: legacy путь — писать прямо в config.py. В production —
    # /opt/citadel/config.py, в dev — <repo>/config.py.
    citadel_home = getattr(config, "CITADEL_HOME", ".")
    config_path = os.path.join(citadel_home, "config.py")
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
        print(f"Error writing to config.py: {e}")
        return False

def run_security_audit():
    """Аудит безопасности системы (Security Agent)"""
    clear_screen()
    theme_color = get_theme_color()
    palette = get_theme_state().current_palette
    reset = palette.reset
    accent = palette.accent


    print(f"{theme_color}==================================================")
    print("           CITADEL OS SECURITY AUDIT              ")
    print(f"=================================================={reset}\n")

    display_progress_bar(1.2, "Scanning configurations and network ports")

    headers = ["Check parameter", "Status", "Risk level", "Recommendation"]
    rows = []

    # 1. Default password check
    # MD5 of admin = "21232f297a57a5a743894a0e4a801fc3"
    default_pass = getattr(config, 'PASSWORD_HASH', '') == "21232f297a57a5a743894a0e4a801fc3"
    if default_pass:
        rows.append(["Administrator password", "Default in use ('admin')", "CRITICAL", "Change the password immediately"])
    else:
        rows.append(["Administrator password", "Changed by user", "NONE", "Update the password regularly"])

    # 2. Debug mode check
    debug_mode = getattr(config, 'DEBUG_MODE', False)
    if debug_mode:
        rows.append(["Debug mode", "ENABLED", "MEDIUM", "Disable it in production"])
    else:
        rows.append(["Debug mode", "DISABLED", "NONE", "No action required"])

    # 3. Root/administrator privileges check
    is_root = False
    if os.name != 'nt':
        is_root = os.getuid() == 0
    else:
        # For Windows check admin privileges
        try:
            is_root = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            # Alternative via net session
            try:
                subprocess.check_call("net session", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                is_root = True
            except Exception:
                is_root = False

    if is_root:
        rows.append(["Superuser privileges", "Running as Root/Admin", "LOW", "Use sudo for individual commands"])
    else:
        rows.append(["Superuser privileges", "Restricted user", "NONE", "System is protected from accidental changes"])

    # 4. Open ports check (quick netstat audit)
    try:
        if os.name == 'nt':
            netstat = subprocess.check_output("netstat -ano", shell=True).decode('cp866')
            # Look for 0.0.0.0 LISTENING
            insecure_listeners = re.findall(r'0\.0\.0\.0:(\d+)\s+.*LISTENING', netstat)
        else:
            ss_bin = getattr(config, "TOOL_SS", "/usr/bin/ss")
            netstat = subprocess.check_output(f"{ss_bin} -tlnp", shell=True).decode('utf-8')
            insecure_listeners = re.findall(r'\*|0\.0\.0\.0:(\d+)', netstat)

        if insecure_listeners:
            ports = ", ".join(set(insecure_listeners[:5]))
            rows.append(["Local network services", f"Open ports: {ports}", "MEDIUM", "Close unneeded services with firewall"])
        else:
            rows.append(["Local network services", "External ports closed", "NONE", "Network filter is OK"])
    except Exception:
        rows.append(["Local network services", "Port analysis unavailable", "LOW", "Check network filter manually"])

    display_table(headers, rows)

    # Summary
    any_high = any(r[2] in ["CRITICAL", "HIGH"] for r in rows)
    any_medium = any(r[2] == "MEDIUM" for r in rows)

    if any_high:
        print(f"\n{accent}[ WARNING ]: Critical security vulnerabilities detected! Take action.{reset}")
    elif any_medium:
        print(f"\n{accent}[ WARNING ]: Medium-severity warnings found.{reset}")
    else:
        print(f"\n{accent}[ SUCCESS ]: Audit passed successfully. No vulnerabilities found.{reset}")

    input("\nPress Enter to continue...")

def run_citadel_center():
    """Citadel Center — interactive control center for Citadel OS."""
    while True:
        clear_screen()
        theme_color = get_theme_color()
        palette = get_theme_state().current_palette
        reset = palette.reset
        accent = palette.accent


        print(f"{theme_color}==================================================")
        print("          CITADEL CENTER - CONTROL HUB            ")
        print(f"=================================================={reset}")
        print(f"User: {accent}{config.USER_NAME}{reset} | Theme: {theme_color}{config.THEME_COLOR}{reset}\n")

        print("[1] Change user name")
        print("[2] Change terminal color theme")
        print("[3] Change administrator password")
        print("[4] Run security audit")
        print("[B] Return to main menu (Back)")

        choice = input("\nSelect settings section: ").strip().lower()

        if choice == '1':
            clear_screen()
            new_name = input("Enter new user name: ").strip()
            if new_name:
                if update_config_value("USER_NAME", new_name):
                    print(f"\n{accent}[ SUCCESS ]: User name successfully changed to '{new_name}'.{reset}")
                else:
                    print("\n[ ERROR ]: Failed to update user name.")
            time.sleep(1)

        elif choice == '2':
            clear_screen()
            print("Available themes:")
            available_themes = [k for k in config.COLORS.keys() if k != "RESET"]
            for idx, theme in enumerate(available_themes, 1):
                c = config.COLORS[theme]
                print(f"[{idx}] {c}{theme}{reset}")

            theme_choice = input("\nSelect theme number: ").strip()
            try:
                idx = int(theme_choice)
                if 1 <= idx <= len(available_themes):
                    selected = available_themes[idx - 1]
                    if update_config_value("THEME_COLOR", selected):
                        print(f"\n{accent}[ SUCCESS ]: Theme successfully changed to {config.COLORS[selected]}{selected}{reset}.")
                    else:
                        print("\n[ ERROR ]: Failed to change theme.")
                else:
                    print("Invalid number.")
            except ValueError:
                print("Invalid input.")
            time.sleep(1.5)

        elif choice == '3':
            clear_screen()
            print(f"{theme_color}=== CHANGE ADMINISTRATOR PASSWORD ==={reset}\n")
            old_pass = input("Enter current password: ").strip()
            new_pass = input("Enter new password: ").strip()
            confirm_pass = input("Confirm new password: ").strip()

            if new_pass != confirm_pass:
                print(f"\n{accent}[ ERROR ]: New passwords do not match!{reset}")
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
