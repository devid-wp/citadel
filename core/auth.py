import hashlib
import sys
import getpass
import config
from core.interface import clear_screen, terminal_print, get_theme_color

def hash_password(password):
    return hashlib.md5(password.encode('utf-8')).hexdigest()

def verify_password(password):
    return hash_password(password) == getattr(config, 'PASSWORD_HASH', '')

def change_password(old_password, new_password):
    """Смена пароля и запись нового хэша в config.py"""
    if not verify_password(old_password):
        return False, "Неверный текущий пароль"
    
    new_hash = hash_password(new_password)
    config_path = "config.py"
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        new_lines = []
        replaced = False
        for line in lines:
            if "PASSWORD_HASH =" in line:
                new_lines.append(f'PASSWORD_HASH = "{new_hash}"  # MD5\n')
                replaced = True
            else:
                new_lines.append(line)
                
        if not replaced:
            # Если строчки не было, вставляем
            new_lines.append(f'\nPASSWORD_HASH = "{new_hash}"\n')
            
        with open(config_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
            
        config.PASSWORD_HASH = new_hash
        return True, "Пароль успешно изменен"
    except Exception as e:
        return False, f"Ошибка записи в файл конфигурации: {e}"

def login_screen():
    """Экран входа в Citadel OS с тремя попытками"""
    clear_screen()
    theme_color = get_theme_color()
    reset = config.COLORS["RESET"]
    red = config.COLORS["RED"]
    
    print(f"{theme_color}##################################################")
    print("         CITADEL OS - СИСТЕМА АВТОРИЗАЦИИ         ")
    print(f"##################################################{reset}\n")
    
    attempts = 3
    while attempts > 0:
        try:
            # Используем input с скрытием ввода, если это терминал, или обычный input с предупреждением
            sys.stdout.write(f"Введите пароль для {config.USER_NAME} (осталось попыток: {attempts}): ")
            sys.stdout.flush()
            password = input().strip()
        except (KeyboardInterrupt, EOFError):
            print("\nАвторизация прервана.")
            sys.exit(1)
            
        if verify_password(password):
            terminal_print("\n[ SUCCESS ]: Авторизация пройдена успешно!", color_code=config.COLORS["GREEN"])
            import time
            time.sleep(0.5)
            return True
        else:
            print(f"{red}[ ERROR ]: Неверный пароль.{reset}\n")
            attempts -= 1
            
    print(f"{red}[ CRITICAL ]: Превышено количество попыток входа. Система заблокирована.{reset}")
    sys.exit(1)
