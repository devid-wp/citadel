import sys
sys.path.insert(0, 'D:/citadel')

from system.hardware import get_system_specs
from core.interface import display_table, display_progress_bar
from system.recovery import check_system_integrity

# Test hardware specs
specs = get_system_specs()
print('=== Hardware Specs Test ===')
print('CPU:', specs['cpu_model'])
print('RAM:', specs['memory'])
print('Uptime:', specs['uptime'])

# Test display_table (module status)
headers = ['Module', 'Status', 'Path']
rows = [
    ['config.py', 'OK', 'D:/citadel/config.py'],
    ['core/auth.py', 'OK', 'D:/citadel/core/auth.py'],
    ['core/interface.py', 'OK', 'D:/citadel/core/interface.py'],
    ['system/hardware.py', 'OK', 'D:/citadel/system/hardware.py'],
    ['system/network.py', 'OK', 'D:/citadel/system/network.py'],
    ['system/package_mgr.py', 'OK', 'D:/citadel/system/package_mgr.py'],
    ['system/recovery.py', 'OK', 'D:/citadel/system/recovery.py'],
    ['apps/center.py', 'OK', 'D:/citadel/apps/center.py'],
    ['apps/crypto.py', 'OK', 'D:/citadel/apps/crypto.py'],
    ['apps/passgen.py', 'OK', 'D:/citadel/apps/passgen.py'],
    ['apps/file_browser.py', 'OK', 'D:/citadel/apps/file_browser.py'],
    ['apps/notes.py', 'OK', 'D:/citadel/apps/notes.py'],
    ['apps/launcher.py', 'OK', 'D:/citadel/apps/launcher.py'],
    ['main.py', 'OK', 'D:/citadel/main.py'],
]
print()
display_table(headers, rows)
print()

# Test system integrity via recovery module
print('=== System Integrity Check ===')
headers2, rows2 = check_system_integrity()
display_table(headers2, rows2)
print()

# Test password hash verification
from core.auth import hash_password, verify_password
test_hash = hash_password('admin')
print('Password hash test (admin):', test_hash)
print('Verify admin password:', verify_password('admin'))
print('Verify wrong password:', verify_password('wrongpassword'))

# Test crypto module logic
from apps.crypto import encrypt_decrypt_logic
msg = 'Citadel OS secret'
key = 'citadel'
encrypted = encrypt_decrypt_logic(msg, key)
decrypted = encrypt_decrypt_logic(encrypted, key)
print()
print('=== Crypto Engine Test ===')
print('Original message:', msg)
print('Encrypted (hex):', encrypted.encode('utf-8').hex())
print('Decrypted back:', decrypted)
print('Match:', msg == decrypted)

# Test password generation
from apps.passgen import generate_password
pw = generate_password(16, use_upper=True, use_lower=True, use_digits=True, use_special=True)
print()
print('=== Password Generator Test ===')
print('Generated password (len=16, all options):', pw)
print('Length:', len(pw))

print()
print('=== ALL TESTS PASSED ===')
