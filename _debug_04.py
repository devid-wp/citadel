"""Debug 0.4 test."""
import sys, os, tempfile, io
sys.path.insert(0, '.')

tmp = tempfile.mkdtemp(prefix="dbg_")
os.chdir(tmp)
with open("echo_helper.py", "w", encoding="utf-8") as fp:
    fp.write("import sys; sys.stdout.write(' '.join(sys.argv[1:]))\n")
with open("alpha.py", "w", encoding="utf-8") as fp:
    fp.write("")
with open("beta.py", "w", encoding="utf-8") as fp:
    fp.write("")
with open("gamma.py", "w", encoding="utf-8") as fp:
    fp.write("")

from core import shell_utils
print("CWD:", os.getcwd())
print("FILES:", os.listdir("."))

# Try directly
buf = io.StringIO()
old = sys.stdout
sys.stdout = buf
rc = shell_utils.run_command("py echo_helper.py *.py")
sys.stdout = old
print("rc:", rc)
print("output:", repr(buf.getvalue()))

# Cleanup
os.chdir("D:\\citadel")
import shutil
shutil.rmtree(tmp, ignore_errors=True)