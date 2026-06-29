"""0.4 Glob expansion smoke test."""
import sys, os, tempfile
sys.path.insert(0, '.')

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

from core.shell_glob import is_glob, expand_token, expand_tokens
from core.shell_tokenizer import tokenize

# Создадим временную директорию с тестовыми файлами
tmp = tempfile.mkdtemp(prefix="citadel_glob_")
try:
    files = [
        "alpha.py", "beta.py", "gamma.py",
        "file1.txt", "file2.txt", "filea.txt",
        ".hidden", "noext",
        "subdir/sub.py",
    ]
    os.makedirs(os.path.join(tmp, "subdir"), exist_ok=True)
    for f in files:
        path = os.path.join(tmp, f)
        with open(path, "w", encoding="utf-8") as fp:
            fp.write("")
    os.chdir(tmp)

    # ---------- Базовые проверки is_glob ----------
    print("\n== is_glob detection ==")
    t = tokenize("ls *.py").tokens[1]
    check("*.py is glob", is_glob(t) is True)
    t = tokenize("ls file?.txt").tokens[1]
    check("file?.txt is glob", is_glob(t) is True)
    t = tokenize("ls [abc].txt").tokens[1]
    check("[abc].txt is glob", is_glob(t) is True)
    t = tokenize("ls plain.txt").tokens[1]
    check("plain.txt is NOT glob", is_glob(t) is False)
    t = tokenize("ls '*.py'").tokens[1]
    check("'*.py' (in quotes) is NOT glob", is_glob(t) is False)

    # ---------- Простые паттерны ----------
    print("\n== simple globs ==")
    t = tokenize("*.py").tokens[0]
    toks = expand_token(t)
    names = sorted(os.path.basename(x.value) for x in toks)
    check("*.py -> 3 .py files", names == ["alpha.py", "beta.py", "gamma.py"],
          f"got: {names}")

    t = tokenize("file?.txt").tokens[0]
    toks = expand_token(t)
    names = sorted(os.path.basename(x.value) for x in toks)
    check("file?.txt -> file[12a].txt",
          names == ["file1.txt", "file2.txt", "filea.txt"],
          f"got: {names}")

    # ---------- Диапазоны ----------
    print("\n== ranges ==")
    t = tokenize("file[1-2].txt").tokens[0]
    toks = expand_token(t)
    names = sorted(os.path.basename(x.value) for x in toks)
    check("file[1-2].txt -> file1+file2",
          names == ["file1.txt", "file2.txt"],
          f"got: {names}")

    # ---------- Отрицание ----------
    t = tokenize("file[!1].txt").tokens[0]
    toks = expand_token(t)
    names = sorted(os.path.basename(x.value) for x in toks)
    check("file[!1].txt -> excludes file1",
          names == ["file2.txt", "filea.txt"],
          f"got: {names}")

    # ---------- Несуществующий паттерн ----------
    print("\n== no matches ==")
    t = tokenize("nonexistent_*.xyz").tokens[0]
    toks = expand_token(t)
    check("nonexistent_*.xyz -> pattern as-is",
          len(toks) == 1 and toks[0].value == "nonexistent_*.xyz",
          f"got: {[x.value for x in toks]}")

    # ---------- Dotfiles по умолчанию скрыты ----------
    print("\n== dotfiles ==")
    t = tokenize("*").tokens[0]
    toks = expand_token(t)
    names = sorted(os.path.basename(x.value) for x in toks)
    check("default * excludes dotfiles",
          ".hidden" not in names and "alpha.py" in names,
          f"got: {names}")

    # ---------- Рекурсивный ** ----------
    print("\n== ** recursion ==")
    t = tokenize("**/*.py").tokens[0]
    toks = expand_token(t)
    basenames = sorted(os.path.basename(x.value) for x in toks)
    check("**/*.py -> 4 files",
          len([n for n in basenames if n.endswith('.py')]) == 4,
          f"got: {basenames}")

    # ---------- expand_tokens (с операторами) ----------
    print("\n== expand_tokens bulk ==")
    # При наличии операторов между шаблонами — должно работать
    line = "echo *.py | cat"
    toks = tokenize(line).tokens
    expanded = expand_tokens(toks)
    word_count = sum(1 for t in expanded if t.kind == "word")
    check("echo *.py | cat -> 5 words (4 files + echo + cat)",
          word_count == 5,
          f"got word_count={word_count}")

    # ---------- Микс glob и обычных слов ----------
    line = "echo hello *.py world"
    toks = tokenize(line).tokens
    expanded = expand_tokens(toks)
    kinds = [t.kind for t in expanded]
    values = [t.value for t in expanded]
    check("echo hello *.py world -> all words, * expands inline",
          kinds == ["word", "word", "word", "word", "word", "word"],
          f"got: {list(zip(kinds, values))}")

    # ---------- Через run_command() — проверяем glob раскрытие в токенах ----------
    print("\n== through run_command (token-level) ==")
    from core import shell_utils
    from core.shell_tokenizer import tokenize
    from core.shell_glob import expand_tokens

    line = "py echo_helper.py *.py"
    toks = tokenize(line).tokens
    expanded = expand_tokens(toks)

    word_values = [t.value for t in expanded if t.kind == "word"]
    check("glob раскрыт: py + helper + 3 .py файла",
          len(word_values) == 5 and word_values[0] == "py"
          and word_values[1] == "echo_helper.py"
          and all(v.endswith(".py") for v in word_values[2:]),
          f"got: {word_values}")

finally:
    # Cleanup
    import shutil
    os.chdir("D:\\citadel")
    shutil.rmtree(tmp, ignore_errors=True)

print()
print("=" * 50)
print(f"  {'ALL 0.4 TESTS PASSED' if errors == 0 else f'{errors} FAILURES'}")
print("=" * 50)