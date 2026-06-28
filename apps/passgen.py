import random
import string
import config
from core.interface import clear_screen, terminal_print, get_theme_color
from core.theme_state import get_theme_state
from rendering.draw_utils import styled_print

def generate_password(length, use_upper=True, use_lower=True, use_digits=True, use_special=True):
    """Генерация надежного пароля по заданным параметрам"""
    chars = ""
    mandatory = []
    
    if use_lower:
        chars += string.ascii_lowercase
        mandatory.append(random.choice(string.ascii_lowercase))
    if use_upper:
        chars += string.ascii_uppercase
        mandatory.append(random.choice(string.ascii_uppercase))
    if use_digits:
        chars += string.digits
        mandatory.append(random.choice(string.digits))
    if use_special:
        specials = "!@#$%^&*()_+-=[]{}|;:,.<>?"
        chars += specials
        mandatory.append(random.choice(specials))
        
    if not chars:
        chars = string.ascii_lowercase + string.digits
        mandatory.append(random.choice(string.ascii_lowercase))
        
    # Заполняем оставшуюся длину
    remaining_length = length - len(mandatory)
    if remaining_length > 0:
        mandatory += [random.choice(chars) for _ in range(remaining_length)]
        
    # Перемешиваем символы
    random.shuffle(mandatory)
    return "".join(mandatory)

def run_passgen():
    """Интерактивный генератор устойчивых паролей"""
    clear_screen()
    theme_color = get_theme_color()
    palette = get_theme_state().current_palette
    reset = palette.reset
    green = palette.accent  # акцент (в NIGHT — RED, иначе YELLOW)

    print(f"{theme_color}=========================================")
    print("        SECURE PASSWORD GENERATOR        ")
    print(f"========================================={reset}\n")

    try:
        length = int(input("Введите длину пароля (рекомендуется от 12): ").strip())
        if length < 4:
            length = 8
    except ValueError:
        length = 12

    use_upper = input("Включать заглавные буквы (A-Z)? (y/n): ").strip().lower() != 'n'
    use_digits = input("Включать цифры (0-9)? (y/n): ").strip().lower() != 'n'
    use_special = input("Включать спецсимволы (!@#$%^&*)? (y/n): ").strip().lower() == 'y'

    password = generate_password(length, use_upper, True, use_digits, use_special)

    print("\n" + "-"*40)
    terminal_print(f"СГЕНЕРИРОВАННЫЙ ПАРОЛЬ: {password}", color_code=green)
    print("-"*40)
    input("\nНажмите Enter для возврата в меню...")
