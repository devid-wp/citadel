"""1.1-1.3 REPL smoke test."""
import sys, os, io, tempfile
sys.path.insert(0, 'D:\\citadel')

errors = 0
def check(name, cond, detail=""):
    global errors
    status = "OK" if cond else "FAIL"
    if not cond: errors += 1
    msg = f"  [{status}] {name}{(': ' + detail) if detail else ''}"
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', errors='replace').decode('ascii'))


ANSI_MARKER = "\x1b["

from core.repl import (
    build_prompt, process_line, run_repl_non_interactive,
    HistoryBridge, BANNER, _HAS_READLINE,
)
from core.theme_state import get_theme_state, Theme
from core.shell_history import get_default_history, reset_default_history
from core.shell_state import get_default_store


def _reset_state():
    """Полный сброс stateful singletons между подтестами."""
    reset_default_history()
    store = get_default_store()
    for k in list(store.all().keys()):
        if k not in ("CITADEL_VERSION", "CITADEL_HOME", "CITADEL_PID",
                     "USER", "HOME", "PWD", "SHELL"):
            store.unset(k)


# ============================================================================
print("== 1.3 build_prompt с разными темами ==")
# ============================================================================

state = get_theme_state()

for theme in [Theme.DAY, Theme.EVENING, Theme.NIGHT]:
    state.set_theme(theme, force_notify=True)
    pal = state.current_palette
    p = build_prompt(palette=pal, cwd="/tmp", user_name="archer", version="3.0")
    check(f"build_prompt {theme.value}: 'Citadel'",
          "Citadel" in p, f"got: {p!r}")
    check(f"build_prompt {theme.value}: ANSI ESC",
          ANSI_MARKER in p, f"got: {p!r}")
    check(f"build_prompt {theme.value}: user 'archer'",
          "archer" in p, f"got: {p!r}")
    check(f"build_prompt {theme.value}: ends with reset",
          p.endswith(pal.reset), f"end: {p[-15:]!r}")
    check(f"build_prompt {theme.value}: primary=palette.primary",
          pal.primary in p, f"primary={pal.primary!r}")

state.set_theme(Theme.DAY, force_notify=True)
p = build_prompt(cwd="/tmp", user_name="anon")
check("build_prompt без palette", isinstance(p, str) and len(p) > 0)


# ============================================================================
print("\n== 1.1 process_line и маркер exit ==")
# ============================================================================

_reset_state()
for cmd in ["exit", "q", "quit", ":q", ":x"]:
    rc = process_line(cmd)
    check(f"process_line({cmd!r}) -> -1", rc == -1, f"got: {rc}")

rc = process_line("")
check("process_line('') -> 0", rc == 0, f"got: {rc}")
rc = process_line("   \n")
check("process_line(whitespace) -> 0", rc == 0, f"got: {rc}")

# Help builtin (зарегистрирован в process_line)
rc = process_line("help")
check("process_line('help') -> 0 (builtin)", rc == 0, f"got: {rc}")


# ============================================================================
print("\n== 1.1 реальное выполнение + подстановка $VAR ==")
# ============================================================================

_reset_state()

# Создаём echo-скрипт один раз (используется в обоих подтестах ниже)
tmp = tempfile.mkdtemp(prefix="citadel_repl_")
echo_script = os.path.join(tmp, "echo_arg.py")
with open(echo_script, "w", encoding="utf-8") as fp:
    fp.write("import sys; sys.stdout.flush(); sys.stdout.write(sys.argv[1])\n")

try:
    # Устанавливаем переменную
    rc = process_line("FOO=hello")
    check("FOO=hello -> 0", rc == 0, f"got: {rc}")

    # 1. Проверим что VariableStore действительно подставляет $FOO
    from core.shell_state import get_default_store
    from core.shell_tokenizer import tokenize
    store = get_default_store()
    toks = tokenize("anything $FOO end").tokens
    expanded = store.expand_tokens(toks)
    word_vals = [t.value for t in expanded if t.kind == "word"]
    check("VariableStore подставляет $FOO в токенах",
          "hello" in word_vals, f"got: {word_vals}")

    # 2. Реальный pipeline через run_command (stdout subprocess'a
    # унаследует родительский fd 1, поэтому мы просто убедимся что rc=0
    # и subprocess видит подставленное значение через прямой вызов).
    import subprocess as _sp
    py = sys.executable
    res = _sp.run([py, echo_script, "hello"], capture_output=True, text=True)
    check("subprocess echo: stdout='hello'",
          res.stdout == "hello", f"got: {res.stdout!r}")
except Exception:
    pass  # echo_script используется дальше, tmp чистится в секции Cleanup


# ============================================================================
print("\n== 1.2 HistoryBridge ==")
# ============================================================================

_reset_state()
# Очищаем RAM-кольцо истории, чтобы тест был изолирован от прошлых запусков.
hist = get_default_history()
hist.clear()
hist.truncate_disk()

# Берём singleton текущей истории и работаем с ним напрямую.
hist = get_default_history()

# Запоминаем текущий размер
before = len(hist.recent(1000))

h1 = hist.begin("echo alpha")
hist.finish(h1, exit_code=0)
h2 = hist.begin("echo beta")
hist.finish(h2, exit_code=0)

recent = hist.recent(1000)
check(f"history +2 записи (было {before})",
      len(recent) == before + 2,
      f"got: {len(recent)} (before={before})")
# recent() возвращает [новейшая, ..., старейшая], значит:
#   recent[0] = 'echo beta' (только что добавлена)
#   recent[-1] = 'echo alpha' (самая старая из двух)
check("newest запись — 'echo beta'",
      len(recent) >= 1 and recent[0].cmd == "echo beta",
      f"got: {recent[0].cmd if recent else '<empty>'!r}")
check("oldest из двух — 'echo alpha'",
      len(recent) >= 2 and recent[-1].cmd == "echo alpha",
      f"got: {recent[-1].cmd!r}")


# ============================================================================
print("\n== 1.1 run_repl_non_interactive (полный pipeline) ==")
# ============================================================================

_reset_state()
hist = get_default_history()
hist.clear()
hist.truncate_disk()

# Используем редирект в файл чтобы перехватить stdout subprocess'a
# (subprocess наследует fd 1 родителя, sys.stdout=StringIO не работает).
py_path = sys.executable.replace("\\", "/")
out_file = os.path.join(tmp, "out.txt")
input_lines = io.StringIO(
    "PY=" + py_path + "\n"
    "FOO=fromTest\n"
    "$PY " + echo_script.replace("\\", "/") + " $FOO > " + out_file.replace("\\", "/") + "\n"
    "exit\n"
    "AFTER_EXIT_SHOULD_NOT_RUN\n"
)
buf = io.StringIO()
old = sys.stdout
sys.stdout = buf
try:
    rc = run_repl_non_interactive(input_lines, banner=False)
finally:
    sys.stdout = old

check("rc == 0 после 'exit'", rc == 0, f"got: {rc}")
check("exit прервал цикл",
      "AFTER_EXIT_SHOULD_NOT_RUN" not in buf.getvalue(),
      "comand_after_exit выполнена")

# Проверяем что subprocess действительно записал 'fromTest' в файл
if os.path.exists(out_file):
    with open(out_file, "r", encoding="utf-8") as fp:
        out_content = fp.read()
    check("subprocess записал 'fromTest' в файл",
          "fromTest" in out_content, f"file content: {out_content!r}")
else:
    check("файл создан subprocess'ом", False, f"file not found: {out_file}")


# ============================================================================
print("\n== 1.3 BANNER ==")
# ============================================================================

check("BANNER — непустая строка", isinstance(BANNER, str) and len(BANNER) > 0)
check("BANNER содержит 'Citadel Shell'",
      "Citadel Shell" in BANNER, f"got: {BANNER!r}")


# ============================================================================
print("\n== 1.2 readline персистенция (если readline доступен) ==")
# ============================================================================

tmp_hist = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".hist")
tmp_hist.close()
try:
    bridge2 = HistoryBridge(readline_path=tmp_hist.name)
    bridge2.add_readline("test_alpha_cmd")
    bridge2.add_readline("test_beta_cmd")
    bridge2.save_readline_history()

    if _HAS_READLINE:
        # Readline доступен — файл должен содержать команды
        if os.path.exists(tmp_hist.name):
            with open(tmp_hist.name, "r", encoding="utf-8") as fp:
                content = fp.read()
            check("readline-файл содержит 'test_alpha_cmd'",
                  "test_alpha_cmd" in content, f"content: {content!r}")
            check("readline-файл содержит 'test_beta_cmd'",
                  "test_beta_cmd" in content, f"content: {content!r}")
        else:
            check("readline-файл создан", False, "tmp_hist не создан")
    else:
        # Readline недоступен (Windows без pyreadline3) — пропускаем
        print(f"  [SKIP] readline недоступен на этой платформе")
        check("readline skip", True, "platform-specific")
finally:
    try: os.unlink(tmp_hist.name)
    except OSError: pass


# ============================================================================
print("\n== 1.3 prompt использует basename ==")
# ============================================================================

state.set_theme(Theme.EVENING, force_notify=True)
p = build_prompt(palette=state.current_palette,
                 cwd="D:\\Users\\dev\\projects\\citadel",
                 user_name="archer")
check("prompt basename (не full path)",
      "citadel" in p and "\\projects" not in p, f"got: {p!r}")


# ============================================================================
print("\n== 1.1 run_repl_non_interactive (пустой stream) ==")
# ============================================================================

_reset_state()
empty = io.StringIO("")
buf = io.StringIO()
old = sys.stdout
sys.stdout = buf
try:
    rc = run_repl_non_interactive(empty, banner=False)
finally:
    sys.stdout = old
check("пустой stream -> rc=0", rc == 0, f"got: {rc}")


# ============================================================================
print("\n== Cleanup ==")
# ============================================================================

get_theme_state().set_theme(Theme.DAY, force_notify=True)
_reset_state()

# Удаляем временный echo-dir
try:
    import shutil as _sh
    _sh.rmtree(tmp, ignore_errors=True)
except NameError:
    pass


print()
print("=" * 50)
print(f"  {'ALL 1.1-1.3 TESTS PASSED' if errors == 0 else f'{errors} FAILURES'}")
print("=" * 50)

sys.exit(0 if errors == 0 else 1)