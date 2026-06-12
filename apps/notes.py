import os
import config
from core.interface import clear_screen, terminal_print, display_table, get_theme_color

NOTES_DIR = "system/notes"

def run_notes_app():
    """Простое консольное приложение заметок для Citadel OS"""
    os.makedirs(NOTES_DIR, exist_ok=True)
    
    while True:
        clear_screen()
        theme_color = get_theme_color()
        reset = config.COLORS["RESET"]
        green = config.COLORS["GREEN"]
        red = config.COLORS["RED"]
        
        print(f"{theme_color}=========================================")
        print("          БЛОКНОТ CITADEL NOTES          ")
        print(f"========================================={reset}")
        print("\n[1] Показать список заметок")
        print("[2] Прочитать заметку")
        print("[3] Создать новую заметку")
        print("[4] Удалить заметку")
        print("[B] Вернуться назад (Back)")
        
        choice = input("\nВыберите действие: ").strip().lower()
        
        if choice == '1':
            clear_screen()
            print(f"{theme_color}=== СПИСОК ВАШИХ ЗАМЕТОК ==={reset}\n")
            try:
                notes = [f for f in os.listdir(NOTES_DIR) if f.endswith(".txt")]
            except Exception as e:
                print(f"Ошибка чтения папки заметок: {e}")
                notes = []
                
            if not notes:
                print("Заметок пока нет. Создайте первую!")
            else:
                for idx, note in enumerate(notes, 1):
                    # Показываем имя без расширения
                    print(f"[{idx}] {note[:-4]}")
            input("\nНажмите Enter для продолжения...")
            
        elif choice == '2':
            clear_screen()
            try:
                notes = [f for f in os.listdir(NOTES_DIR) if f.endswith(".txt")]
            except Exception:
                notes = []
                
            if not notes:
                print("У вас нет сохраненных заметок.")
                input("\nНажмите Enter для продолжения...")
                continue
                
            for idx, note in enumerate(notes, 1):
                print(f"[{idx}] {note[:-4]}")
                
            select = input("\nВыберите номер заметки для чтения: ").strip()
            try:
                num = int(select)
                if 1 <= num <= len(notes):
                    target_note = notes[num - 1]
                    clear_screen()
                    print(f"{theme_color}=== ЗАМЕТКА: {target_note[:-4]} ==={reset}\n")
                    with open(os.path.join(NOTES_DIR, target_note), "r", encoding="utf-8") as f:
                        print(f.read())
                    print(f"\n{theme_color}=================================={reset}")
                else:
                    print("Неверный номер.")
            except ValueError:
                print("Некорректный ввод.")
            input("\nНажмите Enter для продолжения...")
            
        elif choice == '3':
            clear_screen()
            print(f"{theme_color}=== СОЗДАНИЕ ЗАМЕТКИ ==={reset}\n")
            title = input("Введите заголовок заметки: ").strip()
            if not title:
                print("Заголовок не может быть пустым.")
                input("\nНажмите Enter для продолжения...")
                continue
                
            # Заменяем запрещенные символы в имени файла
            filename = "".join(c for c in title if c.isalnum() or c in (' ', '_', '-')).rstrip() + ".txt"
            
            print("\nВведите текст заметки (для сохранения введите ':wq' на новой строке и нажмите Enter):\n")
            lines = []
            while True:
                line = input()
                if line.strip() == ':wq':
                    break
                lines.append(line)
                
            content = "\n".join(lines)
            
            try:
                with open(os.path.join(NOTES_DIR, filename), "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"\n{green}[ SUCCESS ]: Заметка '{title}' успешно сохранена!{reset}")
            except Exception as e:
                print(f"\n{red}[ ERROR ]: Не удалось сохранить заметку: {e}{reset}")
            input("\nНажмите Enter для продолжения...")
            
        elif choice == '4':
            clear_screen()
            try:
                notes = [f for f in os.listdir(NOTES_DIR) if f.endswith(".txt")]
            except Exception:
                notes = []
                
            if not notes:
                print("У вас нет заметок для удаления.")
                input("\nНажмите Enter для продолжения...")
                continue
                
            for idx, note in enumerate(notes, 1):
                print(f"[{idx}] {note[:-4]}")
                
            select = input("\nВыберите номер заметки для удаления: ").strip()
            try:
                num = int(select)
                if 1 <= num <= len(notes):
                    target_note = notes[num - 1]
                    confirm = input(f"{red}Вы действительно хотите удалить '{target_note[:-4]}'? (y/n): {reset}").strip().lower()
                    if confirm == 'y':
                        os.remove(os.path.join(NOTES_DIR, target_note))
                        print(f"{green}Заметка успешно удалена.{reset}")
                else:
                    print("Неверный номер.")
            except ValueError:
                print("Некорректный ввод.")
            input("\nНажмите Enter для продолжения...")
            
        elif choice == 'b':
            break
