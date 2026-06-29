import sys, os, io, tempfile
sys.path.insert(0, '.')

tmp = tempfile.mkdtemp(prefix='cit_repl_')
echo = os.path.join(tmp, 'echo.py')
with open(echo, 'w', encoding='utf-8') as fp:
    fp.write('import sys; sys.stdout.write(sys.argv[1])\n')

print('echo abs:', echo)
print('echo exists:', os.path.exists(echo))

from core.shell_utils import run_command
from core.shell_state import get_default_store

store = get_default_store()
print('FOO before:', store.get('FOO'))

run_command('FOO=hello')
print('FOO after set:', store.get('FOO'))

cmd = sys.executable.replace('\\', '/') + ' ' + echo.replace('\\', '/') + ' $FOO'
print('cmd:', cmd)

buf = io.StringIO()
old = sys.stdout
sys.stdout = buf
try:
    rc = run_command(cmd)
finally:
    sys.stdout = old
print('rc:', rc)
print('out:', repr(buf.getvalue()))

import shutil
shutil.rmtree(tmp)