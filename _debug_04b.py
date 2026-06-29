"""Debug 0.4 with subprocess direct."""
import sys, os, tempfile, subprocess

tmp = tempfile.mkdtemp(prefix="dbg2_")
os.chdir(tmp)
with open("echo_helper.py", "w", encoding="utf-8") as fp:
    fp.write("import sys; sys.stdout.write(' '.join(sys.argv[1:]))\n")
with open("alpha.py", "w", encoding="utf-8") as fp: fp.write("")
with open("beta.py", "w", encoding="utf-8") as fp: fp.write("")
with open("gamma.py", "w", encoding="utf-8") as fp: fp.write("")

print("CWD:", os.getcwd())

# Direct subprocess call
args = ["py", "echo_helper.py", "alpha.py", "beta.py", "gamma.py"]
print("Direct args:", args)
res = subprocess.run(args, capture_output=True, text=True)
print("rc:", res.returncode)
print("stdout:", repr(res.stdout))
print("stderr:", repr(res.stderr))

# Through shell_utils
sys.path.insert(0, "D:\\citadel")
from core import shell_utils
import io
buf = io.StringIO()
old = sys.stdout
sys.stdout = buf
rc = shell_utils.run_command("py echo_helper.py *.py")
sys.stdout = old
print("--- via shell_utils ---")
print("rc:", rc)
print("output:", repr(buf.getvalue()))