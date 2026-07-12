import hashlib
import os
import sys
import time
import getpass
import config
from core.interface import clear_screen, terminal_print, get_theme_color

# bcrypt — современний алгоритм хеширования с автоматической солью.
# MD5 заменён по соображениям безопасности (уязвим к радужным таблицам и коллизиям).
# Если bcrypt недоступен (не установлен), используется fallback на PBKDF2-SHA256,
# который встроен в стандартную библиотеку Python.
try:
    import bcrypt

    _HAS_BCRYPT = True
except ImportError:
    _HAS_BCRYPT = False

# Префикс формата хэша. Позволяет различать алгоритмы и сохранять обратную совместимость.
# Старые хэши (md5$xxx) продолжат работать, пока пользователь не сменит пароль.
HASH_PREFIX_BCRYPT = "bcrypt$"
HASH_PREFIX_PBKDF2 = "pbkdf2$"
HASH_PREFIX_MD5 = "md5$"  # legacy, только для чтения
ITERATIONS = 120_000  # рекомендованное число итераций PBKDF2 (OWASP, 2023)


def _hash_md5(password: str) -> str:
    """Legacy MD5 хэш (только для верификации старых config.py)."""
    return hashlib.md5(password.encode('utf-8')).hexdigest()


def _hash_pbkdf2(password: str, salt: bytes | None = None) -> str:
    """PBKDF2-HMAC-SHA256 с солью. Возвращает строку формата pbkdf2$iter$salt_hex$hash_hex."""
    if salt is None:
        salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return f"{HASH_PREFIX_PBKDF2}{ITERATIONS}${salt.hex()}${derived.hex()}"


def _hash_bcrypt(password: str) -> str:
    """bcrypt с автоматической солью."""
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return f"{HASH_PREFIX_BCRYPT}{hashed.decode('utf-8')}"


def hash_password(password: str) -> str:
    """Хэширование пароля с использованием самого стойкого из доступных алгоритмов."""
    if _HAS_BCRYPT:
        return _hash_bcrypt(password)
    return _hash_pbkdf2(password)


def verify_password(password: str) -> bool:
    """Универсальная проверка пароля: поддерживает bcrypt, PBKDF2 и legacy MD5."""
    stored = getattr(config, 'PASSWORD_HASH', '')

    if not stored:
        return False

    # Новый формат: bcrypt
    if stored.startswith(HASH_PREFIX_BCRYPT) and _HAS_BCRYPT:
        try:
            return bcrypt.checkpw(password.encode("utf-8"), stored[len(HASH_PREFIX_BCRYPT):].encode("utf-8"))
        except Exception:
            return False

    # Новый формат: PBKDF2
    if stored.startswith(HASH_PREFIX_PBKDF2):
        try:
            _, iters, salt_hex, hash_hex = stored.split("$")
            derived = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                bytes.fromhex(salt_hex),
                int(iters),
            )
            return derived.hex() == hash_hex
        except Exception:
            return False

    # Legacy: голый MD5 (старый config.py) — принимаем для обратной совместимости,
    # но при первом успехе рекомендуем обновить.
    if _hash_md5(password) == stored:
        return True

    return False


def change_password(old_password: str, new_password: str):
    """
    Смена пароля с записью нового хэша в config.py.
    Возвращает (success, message).
    """
    if not verify_password(old_password):
        return False, "Неверный текущий пароль"

    if not new_password or len(new_password) < 4:
        return False, "Новый пароль должен содержать минимум 4 символа"

    new_hash = hash_password(new_password)
    config_path = "config.py"

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        new_lines = []
        replaced = False
        for line in lines:
            if line.strip().startswith("PASSWORD_HASH ="):
                new_lines.append(f'PASSWORD_HASH = "{new_hash}"\n')
                replaced = True
            else:
                new_lines.append(line)

        if not replaced:
            new_lines.append(f'\nPASSWORD_HASH = "{new_hash}"\n')

        with open(config_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        config.PASSWORD_HASH = new_hash
        return True, "Пароль успешно изменен"
    except Exception as e:
        return False, f"Ошибка записи в файл конфигурации: {e}"


def login_screen():
    """Экран входа в Citadel OS с тремя попытками и экспоненциальной задержкой."""
    clear_screen()
    theme_color = get_theme_color()
    reset = config.COLORS["RESET"]
    red = config.COLORS["RED"]
    green = config.COLORS["GREEN"]

    print(f"{theme_color}##################################################")
    print("         CITADEL OS - СИСТЕМА АВТОРИЗАЦИИ         ")
    print(f"##################################################{reset}\n")

    # Предупреждение, если пароль ещё в legacy MD5-формате
    stored = getattr(config, 'PASSWORD_HASH', '')
    if stored.startswith(HASH_PREFIX_MD5) or (stored and not stored.startswith("$") and not stored.startswith("bcrypt")):
        # Голый MD5 без префикса
        if not stored.startswith("bcrypt$") and not stored.startswith("pbkdf2$"):
            print(f"{config.COLORS['YELLOW']}[ INFO ]: Используется устаревший формат хранения пароля. Рекомендуется сменить пароль.{reset}\n")

    attempts = 3
    while attempts > 0:
        try:
            sys.stdout.write(f"Введите пароль для {config.USER_NAME} (осталось попыток: {attempts}): ")
            sys.stdout.flush()
            # getpass скрывает ввод от посторонних глаз
            password = getpass.getpass("").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nАвторизация прервана.")
            sys.exit(1)

        if verify_password(password):
            terminal_print("\n[ SUCCESS ]: Авторизация пройдена успешно!", color_code=green)
            time.sleep(0.5)
            return True

        attempts -= 1
        # Экспоненциальная задержка — замедляет brute-force
        delay = 1.0 * (2 ** (3 - attempts))  # 2, 4, 8 секунд
        print(f"{red}[ ERROR ]: Неверный пароль.{reset}")
        if attempts > 0:
            time.sleep(delay)

    print(f"{red}[ CRITICAL ]: Превышено количество попыток входа. Система заблокирована.{reset}")
    sys.exit(1)
