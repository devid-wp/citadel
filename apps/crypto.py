import os
import ast
import base64
import hashlib
import config
from core.interface import clear_screen, terminal_print, get_theme_color, display_progress_bar

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
            raise ValueError("Неверный ключ шифрования")
        except Exception as e:
            raise ValueError(f"Ошибка расшифровки: {e}")

    # Legacy XOR (формат "xor:...")
    if encoded.startswith("xor:"):
        return _xor_fallback(encoded[4:], passphrase)

    raise ValueError("Неизвестный формат шифрования. Ожидается префикс 'ctdl:' или 'xor:'.")


def encrypt_file(path: str, passphrase: str) -> tuple[bool, str]:
    """Шифрование содержимого файла. Возвращает (success, message)."""
    if not os.path.exists(path):
        return False, "Файл не найден"

    try:
        # Бинарный режим, чтобы корректно обрабатывать любые файлы
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

        return True, f"Файл '{path}' успешно зашифрован."
    except Exception as e:
        return False, f"Не удалось зашифровать файл: {e}"


def decrypt_file(path: str, passphrase: str) -> tuple[bool, str]:
    """Расшифровка содержимого файла. Возвращает (success, message)."""
    if not os.path.exists(path):
        return False, "Файл не найден"

    try:
        with open(path, "rb") as f:
            raw = f.read()

        if raw.startswith(FERNET_PREFIX.encode("utf-8")) and _HAS_CRYPTO:
            token = raw[len(FERNET_PREFIX):]
            fernet, _ = _make_fernet(passphrase)
            try:
                data = fernet.decrypt(token)
            except InvalidToken:
                return False, "Неверный ключ шифрования"
        elif raw.startswith(b"xor:"):
            data = _xor_fallback(raw[4:].decode("utf-8", errors="replace"), passphrase).encode("utf-8")
        else:
            return False, "Файл не содержит распознаваемого заголовка шифрования."

        with open(path, "wb") as f:
            f.write(data)

        return True, f"Файл '{path}' успешно расшифрован."
    except Exception as e:
        return False, f"Не удалось расшифровать файл: {e}"


def run_crypto_module():
    """Интерактивное меню модуля шифрования Security Shield."""
    while True:
        clear_screen()
        theme_color = get_theme_color()
        reset = config.COLORS["RESET"]
        green = config.COLORS["GREEN"]
        red = config.COLORS["RED"]
        yellow = config.COLORS["YELLOW"]

        backend = "Fernet (AES-128-CBC + HMAC-SHA256)" if _HAS_CRYPTO else "XOR (FALLBACK — установите 'cryptography')"

        print(f"{theme_color}=========================================")
        print("         SECURE CRYPTO-SHIELD SYSTEM     ")
        print(f"========================================={reset}")
        print(f"\nАлгоритм: {yellow}{backend}{reset}")
        if not _HAS_CRYPTO:
            print(f"{red}ВНИМАНИЕ: cryptography не установлена. Шифрование небезопасно!{reset}")
            print(f"Установите: {cyan}pip install cryptography{reset}".replace("{cyan}", "").replace("{reset}", ""))

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
            try:
                coded = encrypt_string(msg, key)
                print("\n" + "=" * 50)
                print(f"ЗАШИФРОВАННЫЙ ПОТОК (скопируйте целиком):\n{coded}")
                print("=" * 50)
            except Exception as e:
                print(f"{red}[ ERROR ]: {e}{reset}")
            input("\nНажмите Enter для продолжения...")

        elif choice == '2':
            coded_input = input("\nВставьте зашифрованный поток целиком: ").strip()
            key = input("Введите ключ расшифровки: ")
            if not coded_input or not key:
                print("Поток и ключ не могут быть пустыми.")
                input("\nНажмите Enter для продолжения...")
                continue

            try:
                decoded = decrypt_string(coded_input, key)
                print("\n" + "=" * 50)
                terminal_print(f"РАСШИФРОВАННЫЕ ДАННЫЕ:\n{decoded}", color_code=green)
                print("=" * 50)
            except ValueError as e:
                terminal_print(f"\n[ ERROR ]: {e}", color_code=red)
            except Exception as e:
                terminal_print(f"\n[ ERROR ]: Ошибка декодирования ({e}).", color_code=red)
            input("\nНажмите Enter для продолжения...")

        elif choice == '3':
            filepath = input("\nВведите путь к файлу: ").strip()
            key = input("Введите ключ шифрования: ")
            if not key:
                print("Ключ не может быть пустым.")
                input("\nНажмите Enter для продолжения...")
                continue

            display_progress_bar(0.8, "Шифрование файла")
            ok, msg = encrypt_file(filepath, key)
            print(f"{green if ok else red}[ {'SUCCESS' if ok else 'ERROR'} ]: {msg}{reset}")
            input("\nНажмите Enter для продолжения...")

        elif choice == '4':
            filepath = input("\nВведите путь к файлу: ").strip()
            key = input("Введите ключ шифрования: ")
            if not key:
                print("Ключ не может быть пустым.")
                input("\nНажмите Enter для продолжения...")
                continue

            display_progress_bar(0.8, "Расшифровка файла")
            ok, msg = decrypt_file(filepath, key)
            print(f"{green if ok else red}[ {'SUCCESS' if ok else 'ERROR'} ]: {msg}{reset}")
            input("\nНажмите Enter для продолжения...")

        elif choice == 'b':
            break
