import os
import sys
import config
from core.interface import clear_screen, terminal_print, get_theme_color, display_progress_bar

def encrypt_decrypt_logic(text, key):
    """XOR-алгоритм для шифрования конфиденциальных файлов и строк"""
    if not key:
        return text
    output = []
    for i, char in enumerate(text):
        key_char = key[i % len(key)]
        output.append(chr(ord(char) ^ ord(key_char)))
    return "".join(output)

def run_crypto_module():
    """Интерактивное меню модуля шифрования Security Shield"""
    while True:
        clear_screen()
        theme_color = get_theme_color()
        reset = config.COLORS["RESET"]
        green = config.COLORS["GREEN"]
        red = config.COLORS["RED"]
        
        print(f"{theme_color}=========================================")
        print("         SECURE CRYPTO-SHIELD SYSTEM     ")
        print(f"========================================={reset}")
        print("\n[1] Зашифровать строку данных (Encrypt)")
        print("[2] Расшифровать строку данных (Decrypt)")
        print("[3] Зашифровать файл (Encrypt File)")
        print("[4] Расшифровать файл (Decrypt File)")
        print("[B] Вернуться назад (Back)")
        
        choice = input("\nВыберите опцию: ").strip().lower()
        
        if choice == '1':
            msg = input("\nВведите конфиденциальный текст: ")
            key = input("Введите ключ шифрования (пароль): ")
            if not msg or not key:
                print("Текст и ключ не могут быть пустыми.")
                input("\nНажмите Enter для продолжения...")
                continue
            coded = encrypt_decrypt_logic(msg, key)
            print("\n" + "="*50)
            print(f"ЗАШИФРОВАННЫЙ ПОТОК (HEX):\n{coded.encode('utf-8').hex()}")
            print(f"ЗАШИФРОВАННЫЙ ПОТОК (REPR):\n{repr(coded)}")
            print("="*50)
            input("\nНажмите Enter для продолжения...")
            
        elif choice == '2':
            coded_input = input("\nВставьте зашифрованный поток (HEX или REPR): ").strip()
            key = input("Введите ключ расшифровки: ")
            if not coded_input or not key:
                print("Поток и ключ не могут быть пустыми.")
                input("\nНажмите Enter для продолжения...")
                continue
                
            try:
                # Пробуем декодировать из HEX
                try:
                    actual_str = bytes.fromhex(coded_input).decode('utf-8')
                except ValueError:
                    # Если не HEX, пробуем eval
                    actual_str = eval(coded_input)
                    
                decoded = encrypt_decrypt_logic(actual_str, key)
                print("\n" + "="*50)
                terminal_print(f"РАСШИФРОВАННЫЕ ДАННЫЕ:\n{decoded}", color_code=green)
                print("="*50)
            except Exception as e:
                terminal_print(f"\n[ ERROR ]: Ошибка декодирования. Неверный формат или ключ ({e}).", color_code=red)
            input("\nНажмите Enter для продолжения...")
            
        elif choice == '3' or choice == '4':
            filepath = input("\nВведите путь к файлу: ").strip()
            if not os.path.exists(filepath):
                print(f"{red}[ ERROR ]: Файл не найден.{reset}")
                input("\nНажмите Enter для продолжения...")
                continue
                
            key = input("Введите ключ шифрования: ")
            if not key:
                print("Ключ не может быть пустым.")
                input("\nНажмите Enter для продолжения...")
                continue
                
            try:
                display_progress_bar(1.0, "Обработка файла")
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    
                processed_content = encrypt_decrypt_logic(content, key)
                
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(processed_content)
                    
                action = "зашифрован" if choice == '3' else "расшифрован"
                print(f"{green}[ SUCCESS ]: Файл '{filepath}' успешно {action}.{reset}")
            except Exception as e:
                print(f"{red}[ ERROR ]: Не удалось обработать файл: {e}{reset}")
            input("\nНажмите Enter для продолжения...")
            
        elif choice == 'b':
            break
