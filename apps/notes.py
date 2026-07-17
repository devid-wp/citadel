import os
import config
from core.interface import clear_screen, terminal_print, display_table, get_theme_color
from core.theme_state import get_theme_state
from rendering.draw_utils import styled_print

# Папка с заметками. В production — /root/.config/citadel/notes/, в dev — system/notes/.
NOTES_DIR = getattr(config, "CITADEL_NOTES_DIR", "system/notes")

def run_notes_app():
    """Simple console notes app for Citadel OS."""
    os.makedirs(NOTES_DIR, exist_ok=True)

    while True:
        clear_screen()
        theme_color = get_theme_color()
        palette = get_theme_state().current_palette
        reset = palette.reset
        accent = palette.accent


        print(f"{theme_color}=========================================")
        print("          CITADEL NOTES NOTEBOOK          ")
        print(f"========================================={reset}")
        print("\n[1] Show list of notes")
        print("[2] Read a note")
        print("[3] Create a new note")
        print("[4] Delete a note")
        print("[B] Return to previous menu (Back)")

        choice = input("\nSelect an action: ").strip().lower()

        if choice == '1':
            clear_screen()
            print(f"{theme_color}=== LIST OF YOUR NOTES ==={reset}\n")
            try:
                notes = [f for f in os.listdir(NOTES_DIR) if f.endswith(".txt")]
            except Exception as e:
                print(f"Error reading notes folder: {e}")
                notes = []

            if not notes:
                print("No notes yet. Create your first one!")
            else:
                for idx, note in enumerate(notes, 1):
                    # Show name without the extension
                    print(f"[{idx}] {note[:-4]}")
            input("\nPress Enter to continue...")

        elif choice == '2':
            clear_screen()
            try:
                notes = [f for f in os.listdir(NOTES_DIR) if f.endswith(".txt")]
            except Exception:
                notes = []

            if not notes:
                print("You have no saved notes.")
                input("\nPress Enter to continue...")
                continue

            for idx, note in enumerate(notes, 1):
                print(f"[{idx}] {note[:-4]}")

            select = input("\nSelect the number of the note to read: ").strip()
            try:
                num = int(select)
                if 1 <= num <= len(notes):
                    target_note = notes[num - 1]
                    clear_screen()
                    print(f"{theme_color}=== NOTE: {target_note[:-4]} ==={reset}\n")
                    with open(os.path.join(NOTES_DIR, target_note), "r", encoding="utf-8") as f:
                        print(f.read())
                    print(f"\n{theme_color}=================================={reset}")
                else:
                    print("Invalid number.")
            except ValueError:
                print("Invalid input.")
            input("\nPress Enter to continue...")

        elif choice == '3':
            clear_screen()
            print(f"{theme_color}=== CREATE A NOTE ==={reset}\n")
            title = input("Enter the note title: ").strip()
            if not title:
                print("Title must not be empty.")
                input("\nPress Enter to continue...")
                continue

            # Strip forbidden characters from the file name
            filename = "".join(c for c in title if c.isalnum() or c in (' ', '_', '-')).rstrip() + ".txt"

            print("\nEnter the note text (to save, type ':wq' on a new line and press Enter):\n")
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
                print(f"\n{accent}[ SUCCESS ]: Note '{title}' saved successfully!{reset}")
            except Exception as e:
                print(f"\n{accent}[ ERROR ]: Failed to save note: {e}{reset}")
            input("\nPress Enter to continue...")

        elif choice == '4':
            clear_screen()
            try:
                notes = [f for f in os.listdir(NOTES_DIR) if f.endswith(".txt")]
            except Exception:
                notes = []

            if not notes:
                print("You have no notes to delete.")
                input("\nPress Enter to continue...")
                continue

            for idx, note in enumerate(notes, 1):
                print(f"[{idx}] {note[:-4]}")

            select = input("\nSelect the number of the note to delete: ").strip()
            try:
                num = int(select)
                if 1 <= num <= len(notes):
                    target_note = notes[num - 1]
                    confirm = input(f"{accent}Are you sure you want to delete '{target_note[:-4]}'? (y/n): {reset}").strip().lower()
                    if confirm == 'y':
                        os.remove(os.path.join(NOTES_DIR, target_note))
                        print(f"{accent}Note deleted successfully.{reset}")
                else:
                    print("Invalid number.")
            except ValueError:
                print("Invalid input.")
            input("\nPress Enter to continue...")

        elif choice == 'b':
            break
