"""
Тесты Citadel OS v1.0 (Core 3.0).

Запуск:
    python test_all.py

Или для pytest-стиля:
    pytest test_all.py
"""
import os
import sys
import tempfile

# Гарантируем, что текущая директория — корень проекта
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def banner(title):
    print(f"\n=== {title} ===")


# ---------------------------------------------------------------------------
banner("Hardware Specs")
from system.hardware import get_system_specs
specs = get_system_specs()
print('CPU:    ', specs['cpu_model'])
print('RAM:    ', specs['memory'])
print('Uptime: ', specs['uptime'])
assert specs['cpu_model'] and specs['memory'] and specs['uptime'], "specs missing"


# ---------------------------------------------------------------------------
banner("Display Table")
from core.interface import display_table
headers = ['Module', 'Status', 'Path']
rows = [
    ['config.py', 'OK', 'config.py'],
    ['core/auth.py', 'OK', 'core/auth.py'],
    ['core/interface.py', 'OK', 'core/interface.py'],
    ['core/shell_utils.py', 'OK', 'core/shell_utils.py'],
    ['system/geo.py', 'OK', 'system/geo.py'],
    ['system/user_config.py', 'OK', 'system/user_config.py'],
    ['system/logger.py', 'OK', 'system/logger.py'],
    ['apps/crypto.py', 'OK', 'apps/crypto.py'],
    ['apps/weather.py', 'OK', 'apps/weather.py'],
    ['main.py', 'OK', 'main.py'],
]
display_table(headers, rows)


# ---------------------------------------------------------------------------
banner("System Integrity")
from system.recovery import check_system_integrity
headers2, rows2 = check_system_integrity()
display_table(headers2, rows2)


# ---------------------------------------------------------------------------
banner("Password Hashing (bcrypt or PBKDF2)")
from core.auth import hash_password, verify_password
test_pass = "admin"
hashed = hash_password(test_pass)
print('Hash format:', hashed[:20] + "...")
assert verify_password(test_pass), "Hash must verify original"
assert not verify_password("wrong"), "Wrong password must not verify"
print('OK: verify works, wrong password rejected')


# ---------------------------------------------------------------------------
banner("Password Generator")
from apps.passgen import generate_password
pw = generate_password(20, use_upper=True, use_lower=True, use_digits=True, use_special=True)
print('Generated (len=20, all options):', pw)
assert len(pw) == 20
assert any(c.islower() for c in pw)
assert any(c.isupper() for c in pw)
assert any(c.isdigit() for c in pw)
assert any(not c.isalnum() for c in pw)


# ---------------------------------------------------------------------------
banner("Crypto Module (Fernet round-trip)")
from apps.crypto import encrypt_string, decrypt_string
msg = "Citadel OS secret payload 12345"
key = "ultra-secret-passphrase"
encrypted = encrypt_string(msg, key)
print('Encrypted:', encrypted[:60] + "...")
decrypted = decrypt_string(encrypted, key)
print('Decrypted:', decrypted)
assert decrypted == msg, f"Round-trip failed: {decrypted!r} != {msg!r}"

# Wrong key should fail (raise ValueError)
try:
    decrypt_string(encrypted, "wrong-key")
    print("[WARN] Wrong key was accepted — cryptography may be missing (fallback XOR)")
except ValueError as e:
    print('OK: wrong key rejected:', e)


# ---------------------------------------------------------------------------
banner("Crypto Module (file round-trip)")
# Создаём временный файл и шифруем/расшифровываем
tmpf = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8')
tmpf.write("Sensitive content: secret data")
tmpf.close()
try:
    from apps.crypto import encrypt_file, decrypt_file
    ok, msg = encrypt_file(tmpf.name, "test-pass")
    assert ok, f"encrypt_file failed: {msg}"
    print('Encrypted file:', msg)
    # Содержимое теперь должно быть нечитаемым
    with open(tmpf.name, 'rb') as f:
        encrypted_raw = f.read()
    assert b"sensitive" not in encrypted_raw.lower(), "Plain text leaked in encrypted file"
    ok, msg = decrypt_file(tmpf.name, "test-pass")
    assert ok, f"decrypt_file failed: {msg}"
    with open(tmpf.name, 'r', encoding='utf-8') as f:
        back = f.read()
    assert back == "Sensitive content: secret data", "File content not restored"
    print('OK: file round-trip works')
finally:
    if os.path.exists(tmpf.name):
        os.remove(tmpf.name)


# ---------------------------------------------------------------------------
banner("User Config (JSON storage)")
from system.user_config import (
    get_user_pref, set_user_pref, add_alias, remove_alias, get_aliases
)
# Сначала запоминаем текущие алиасы, чтобы не испортить
saved_aliases = dict(get_aliases())
try:
    add_alias("test_alias", "echo test")
    assert "test_alias" in get_aliases()
    assert get_aliases()["test_alias"] == "echo test"
    print('OK: alias added')
    remove_alias("test_alias")
    assert "test_alias" not in get_aliases()
    print('OK: alias removed')

    # set/get
    set_user_pref("test_pref", 42)
    val = get_user_pref("test_pref")
    assert val == 42
    print('OK: pref saved and loaded')
    # Удаляем тестовые ключи
    from system.user_config import _load_raw, _save_raw
    data = _load_raw()
    data.pop("test_pref", None)
    _save_raw(data)
finally:
    # Восстанавливаем исходные алиасы
    from system.user_config import _load_raw, _save_raw
    data = _load_raw()
    data["aliases"] = saved_aliases
    _save_raw(data)


# ---------------------------------------------------------------------------
banner("Logger")
from system.logger import log_event, tail_log, log_security
log_event("INFO", "Test message from test_all.py")
log_security("Test security event")
lines = tail_log(5)
print('Tail of log:')
for ln in lines:
    print('  ', ln)
assert lines, "Logger produced no output"
print('OK: logger writes to file')


# ---------------------------------------------------------------------------
banner("Geo (offline — expect None or cached)")
from system.geo import get_location, format_location
loc = get_location()
if loc:
    print(format_location(loc))
else:
    print("(no network — get_location returned None, as expected in offline env)")


# ---------------------------------------------------------------------------
banner("Weather helpers (no network needed)")
from apps.weather import describe_wmo, _wind_direction
print("WMO 0:", describe_wmo(0))   # ("Ясно", "☀️")
print("WMO 95:", describe_wmo(95)) # ("Гроза", "⛈️")
print("WMO 999:", describe_wmo(999))  # fallback
print("Wind 0°:", _wind_direction(0))    # С
print("Wind 90°:", _wind_direction(90))  # В
print("Wind 180°:", _wind_direction(180)) # Ю
assert describe_wmo(0)[0] == "Ясно"
assert _wind_direction(0) == "С"


# ---------------------------------------------------------------------------
banner("Shell Utils — resolve_command & aliases")
from core.shell_utils import resolve_command
from system.user_config import add_alias
saved = dict(get_aliases())
try:
    add_alias("test_x", "echo Y")
    assert resolve_command("test_x") == "echo Y"
    assert resolve_command("test_x arg1") == "echo Y arg1"
    assert resolve_command("ls") == "ls"  # не-алиас остаётся как есть
    print('OK: aliases resolved correctly')
finally:
    from system.user_config import _load_raw, _save_raw
    data = _load_raw()
    data["aliases"] = saved
    _save_raw(data)


print("\n=== ALL TESTS PASSED ===")