import os
import shutil
import sys

# Пути (подставь свои, если отличаются)
SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
ISO_BUILD_DIR = r"D:\citadel_os_ISO"
TARGET_DIR = os.path.join(ISO_BUILD_DIR, "airootfs", "usr", "share", "citadel")

# Списки файлов и папок, которые нужно перенести
INCLUDE_PATHS = ["core", "system", "apps", "main.py", "main_handlers.py", "config.py", "requirements.txt"]

def clean_pycache(target):
    """Удаляет скомпилированные файлы __pycache__ из целевой директории."""
    for root, dirs, files in os.walk(target):
        if "__pycache__" in dirs:
            pycache_path = os.path.join(root, "__pycache__")
            shutil.rmtree(pycache_path)

def main():
    print("[*] Старт подготовки исходного кода Citadel для ISO...")
    
    if not os.path.exists(ISO_BUILD_DIR):
        print(f"[!] Ошибка: Сборочная директория {ISO_BUILD_DIR} не найдена.")
        sys.exit(1)

    # Очищаем старый билд исходников, если он был
    if os.path.exists(TARGET_DIR):
        print("[*] Очистка старых исходников в target...")
        shutil.rmtree(TARGET_DIR)
        
    os.makedirs(TARGET_DIR, exist_ok=True)

    # Копируем структуру
    for path_name in INCLUDE_PATHS:
        src_path = os.path.join(SOURCE_DIR, path_name)
        dst_path = os.path.join(TARGET_DIR, path_name)
        
        if not os.path.exists(src_path):
            print(f"[?] Пропуск: {path_name} не найден в источнике.")
            continue
            
        print(f"[+] Копирование: {path_name} -> ISO rootfs")
        if os.path.isdir(src_path):
            shutil.copytree(src_path, dst_path)
        else:
            shutil.copy2(src_path, dst_path)

    # Очистка от мусора разработки
    clean_pycache(TARGET_DIR)
    
    # Гарантируем отсутствие локальных логов и конфигов в ISO, чтобы не тащить чужие пароли
    for private_file in ["citadel.log", "user_config.json"]:
        private_path = os.path.join(TARGET_DIR, "system", private_file)
        if os.path.exists(private_path):
            os.remove(private_path)
            print(f"[-] Удален локальный файл данных: {private_file}")

    print(f"\n[📊] Сборка подготовлена успешно!")
    print(f"Исходный код Citadel изолирован в: {TARGET_DIR}")
    print("Теперь можно переносить папку D:\\citadel_os_ISO на машину с Arch Linux для запуска mkarchiso.")

if __name__ == "__main__":
    main()