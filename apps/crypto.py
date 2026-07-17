import os
import ast
import base64
import hashlib
import config
from core.interface import clear_screen, terminal_print, get_theme_color, display_progress_bar
from core.theme_state import get_theme_state
from rendering.draw_utils import styled_print

# Реальное AES-шифрование с аутентификацией (Fernet = AES-128-CBC + HMAC-SHA256).
# Заменяет уязвимый XOR из предыдущей версии.
try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False


# Хранилище зашифрованных заметок и файлов использует префикс "ctdl:" —
# чтобы можно было отличить новый формат от XOR-блобов прошлых версий.
FERNET_PREFIX = "ctdl:"


def _derive_key(passphrase: str, salt: bytes | None = None) -> bytes:
    """
    Получение 32-байтного ключа Fernet из парольной фразы через PBKDF2-HMAC-SHA256.
    PBKDF2 даёт устойчивость к перебору по словарю.

    Соль может быть:
    - передана извне (для шифрования файлов — хранится в префиксе payload);
    - None (Fernet сам эфемерно использует случайный nonce в каждом токене,
      поэтому для строк и так безопасно).
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt or b"citadel-fernet-salt-v1",
        iterations=120_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def _make_fernet(passphrase: str, salt: bytes | None = None):
    """
    Создаёт Fernet с ключом, выведенным из парольной фразы.
    Соль либо передаётся (для дешифрования), либо None (Fernet-токен несёт свою соль).
    """
    key = _derive_key(passphrase, salt)
    return Fernet(key), salt


def _xor_fallback(text: str, key: str) -> str:
    """Legacy XOR — только для обратной совместимости со старыми зашифрованными заметками."""
    if not key:
        return text
    output = []
    for i, char in enumerate(text):
        key_char = key[i % len(key)]
        output.append(chr(ord(char) ^ ord(key_char)))
    return "".join(output)


def encrypt_string(text: str, passphrase: str) -> str:
    """
    Шифрование строки. Возвращает строку формата:
    "ctdl:<fernet_token>"

    Fernet сам включает в токен свою случайную соль (nonce) для каждого сообщения,
    поэтому одна и та же парольная фраза даёт разные токены при повторе.
    """
    if _HAS_CRYPTO:
        fernet, _ = _make_fernet(passphrase)
        token = fernet.encrypt(text.encode("utf-8"))
        return f"{FERNET_PREFIX}{token.decode()}"

    # Fallback — если cryptography не установлена (только для ознакомления)
    return f"xor:{_xor_fallback(text, passphrase)}"


def decrypt_string(encoded: str, passphrase: str) -> str:
    """
    Расшифровка строки. Поддерживает новый формат (ctdl:...) и legacy XOR (xor:...).
    Бросает ValueError, если формат неизвестен или ключ неверный.
    """
    encoded = encoded.strip()

    # Новый формат: ctdl:<token>
    if encoded.startswith(FERNET_PREFIX) and _HAS_CRYPTO:
        try:
            token = encoded[len(FERNET_PREFIX):].encode("utf-8")
            fernet, _ = _make_fernet(passphrase)
            return fernet.decrypt(token).decode("utf-8")
        except InvalidToken:
            raise ValueError("Invalid encryption key")
        except Exception as e:
            raise ValueError(f"Decryption error: {e}")

    # Legacy XOR (формат "xor:...")
    if encoded.startswith("xor:"):
        return _xor_fallback(encoded[4:], passphrase)

    raise ValueError("Unknown encryption format. Expected prefix 'ctdl:' or 'xor:'.")


def encrypt_file(path: str, passphrase: str) -> tuple[bool, str]:
    """Encrypt file contents. Returns (success, message)."""
    if not os.path.exists(path):
        return False, "File not found"

    try:
        # Binary mode so we handle any file type correctly
        with open(path, "rb") as f:
            data = f.read()

        if _HAS_CRYPTO:
            fernet, _ = _make_fernet(passphrase)
            token = fernet.encrypt(data)
            payload = token
            header = FERNET_PREFIX.encode("utf-8")
        else:
            payload = _xor_fallback(data.decode("utf-8", errors="replace"), passphrase).encode("utf-8")
            header = b"xor:"

        with open(path, "wb") as f:
            f.write(header + payload)

        return True, f"File '{path}' encrypted successfully."
    except Exception as e:
        return False, f"Failed to encrypt file: {e}"


def decrypt_file(path: str, passphrase: str) -> tuple[bool, str]:
    """Decrypt file contents. Returns (success, message)."""
    if not os.path.exists(path):
        return False, "File not found"

    try:
        with open(path, "rb") as f:
            raw = f.read()

        if raw.startswith(FERNET_PREFIX.encode("utf-8")) and _HAS_CRYPTO:
            token = raw[len(FERNET_PREFIX):]
            fernet, _ = _make_fernet(passphrase)
            try:
                data = fernet.decrypt(token)
            except InvalidToken:
                return False, "Invalid encryption key"
        elif raw.startswith(b"xor:"):
            data = _xor_fallback(raw[4:].decode("utf-8", errors="replace"), passphrase).encode("utf-8")
        else:
            return False, "File has no recognized encryption header."

        with open(path, "wb") as f:
            f.write(data)

        return True, f"File '{path}' decrypted successfully."
    except Exception as e:
        return False, f"Failed to decrypt file: {e}"


def run_crypto_module():
    """Interactive Security Shield encryption module menu."""
    while True:
        clear_screen()
        theme_color = get_theme_color()
        palette = get_theme_state().current_palette
        reset = palette.reset
        # accent: in DAY/EVENING — YELLOW, in NIGHT — RED (used for
        # success, error, and warning alike).
        accent = palette.accent

        backend = "Fernet (AES-128-CBC + HMAC-SHA256)" if _HAS_CRYPTO else "XOR (FALLBACK — install 'cryptography')"

        print(f"{theme_color}=========================================")
        print("         SECURE CRYPTO-SHIELD SYSTEM     ")
        print(f"========================================={reset}")
        print(f"\nAlgorithm: {accent}{backend}{reset}")
        if not _HAS_CRYPTO:
            print(f"{accent}WARNING: 'cryptography' is not installed. Encryption is unsafe!{reset}")
            print(f"Install with: {accent}pip install cryptography{reset}")

        print("\n[1] Encrypt a string of data (Encrypt)")
        print("[2] Decrypt a string of data (Decrypt)")
        print("[3] Encrypt a file (Encrypt File)")
        print("[4] Decrypt a file (Decrypt File)")
        print("[B] Return to previous menu (Back)")

        choice = input("\nSelect an option: ").strip().lower()

        if choice == '1':
            msg = input("\nEnter the confidential text: ")
            key = input("Enter the encryption key (passphrase): ")
            if not msg or not key:
                print("Text and key must not be empty.")
                input("\nPress Enter to continue...")
                continue
            try:
                coded = encrypt_string(msg, key)
                print("\n" + "=" * 50)
                print(f"ENCRYPTED STREAM (copy it in full):\n{coded}")
                print("=" * 50)
            except Exception as e:
                print(f"{accent}[ ERROR ]: {e}{reset}")
            input("\nPress Enter to continue...")

        elif choice == '2':
            coded_input = input("\nPaste the encrypted stream in full: ").strip()
            key = input("Enter the decryption key: ")
            if not coded_input or not key:
                print("Stream and key must not be empty.")
                input("\nPress Enter to continue...")
                continue

            try:
                decoded = decrypt_string(coded_input, key)
                print("\n" + "=" * 50)
                terminal_print(f"DECRYPTED DATA:\n{decoded}", color_code=accent)
                print("=" * 50)
            except ValueError as e:
                terminal_print(f"\n[ ERROR ]: {e}", color_code=accent)
            except Exception as e:
                terminal_print(f"\n[ ERROR ]: Decoding error ({e}).", color_code=accent)
            input("\nPress Enter to continue...")

        elif choice == '3':
            filepath = input("\nEnter the file path: ").strip()
            key = input("Enter the encryption key: ")
            if not key:
                print("Key must not be empty.")
                input("\nPress Enter to continue...")
                continue

            display_progress_bar(0.8, "Encrypting file")
            ok, msg = encrypt_file(filepath, key)
            print(f"{accent}[ {'SUCCESS' if ok else 'ERROR'} ]: {msg}{reset}")
            input("\nPress Enter to continue...")

        elif choice == '4':
            filepath = input("\nEnter the file path: ").strip()
            key = input("Enter the encryption key: ")
            if not key:
                print("Key must not be empty.")
                input("\nPress Enter to continue...")
                continue

            display_progress_bar(0.8, "Decrypting file")
            ok, msg = decrypt_file(filepath, key)
            print(f"{accent}[ {'SUCCESS' if ok else 'ERROR'} ]: {msg}{reset}")
            input("\nPress Enter to continue...")

        elif choice == 'b':
            break
