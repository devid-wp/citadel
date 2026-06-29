"""0.5 Background jobs smoke test."""
import sys, os, time, io
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


from core.shell_jobs import (
    JobTable, BackgroundJob, JobState,
    get_default_job_table, reset_default_job_table,
)
from core.shell_pipeline import parse_pipeline, execute_commandline
from core.shell_tokenizer import tokenize

# Reset singleton for fresh state
reset_default_job_table()


# ============================================================================
print("== JobTable базовые операции ==")
# ============================================================================

table = JobTable()
jid1 = table.allocate_id()
check("allocate_id возвращает int", isinstance(jid1, int))
check("allocate_id монотонный", table.allocate_id() > jid1)


# ============================================================================
print("\n== Фоновый процесс: запуск и ожидание ==")
# ============================================================================

# Короткая команда которая засыпает, чтобы мы успели проверить состояние
line = "ping 127.0.0.1 -n 3"  # Windows ping ждёт N секунд
toks = tokenize(line).tokens
stages = parse_pipeline(toks)
# Принудительно ставим background для теста (имитируем `cmd &`)
stages[-1].background = True

from core.shell_jobs import run_stages_in_background
job = run_stages_in_background(
    get_default_job_table(),
    stages,
    command=line,
)
check("job создан", job is not None)
check("job_id назначен", job.job_id > 0)
check("job state = RUNNING", job.state == JobState.RUNNING)
check("job has process", len(job.processes) > 0)

# Сразу проверяем что процесс активен
time.sleep(0.3)
check("job.is_alive() == True", job.is_alive())

# Ждём завершения
table2 = get_default_job_table()
rc = table2.wait(job.job_id, timeout=15)
check("wait вернул exit_code", rc is not None, f"got: {rc}")
check("job.state стал EXITED", job.state == JobState.EXITED)
check("exit_code 0 (ping success)", rc == 0, f"got: {rc}")


# ============================================================================
print("\n== execute_commandline с background через `&` ==")
# ============================================================================

# Проверяем что execute_commandline с `&` запускает в фоне
line = "ping 127.0.0.1 -n 2 &"
toks = tokenize(line).tokens
check("& токенизирован как background", any(t.kind == "background" for t in toks))

start = time.time()
rc = execute_commandline(toks, raw_command=line)
elapsed = time.time() - start

check("rc=0 после &", rc == 0, f"got: {rc}")
check("вернулся быстро (< 1s), не дожидаясь ping",
      elapsed < 1.5, f"elapsed={elapsed:.2f}s")

# Job должен быть в таблице
all_jobs = get_default_job_table().all()
check("есть хотя бы 1 фоновый job", len(all_jobs) >= 1,
      f"got {len(all_jobs)} jobs")

# Дождёмся
time.sleep(2.5)
get_default_job_table().all()  # refresh


# ============================================================================
print("\n== _builtin_jobs ==")
# ============================================================================

# Перенаправляем stdout чтобы прочитать вывод
from core import shell_utils
buf = io.StringIO()
old = sys.stdout
sys.stdout = buf
try:
    rc = shell_utils._builtin_jobs([])
    sys.stdout = old
    out = buf.getvalue()
    check("jobs rc=0", rc == 0)
finally:
    sys.stdout = old

# Также проверим `jobs -l` — там должны быть exited jobs
buf = io.StringIO()
sys.stdout = buf
try:
    rc = shell_utils._builtin_jobs(["-l"])
    sys.stdout = old
    out = buf.getvalue()
    check("jobs -l rc=0", rc == 0, f"got: {rc}")
    check("jobs -l показывает заголовок", "ID" in out, f"out: {out!r}")
finally:
    sys.stdout = old


# ============================================================================
print("\n== _builtin_wait ==")
# ============================================================================

# Запустим ещё один background
line = "ping 127.0.0.1 -n 2 &"
toks = tokenize(line).tokens
execute_commandline(toks, raw_command=line)

# Найдём свежий running job
running = [j for j in get_default_job_table().running()]
check("есть running job после &", len(running) >= 1, f"got {len(running)}")

if running:
    jid = running[0].job_id
    start = time.time()
    rc = shell_utils._builtin_wait([str(jid)])
    elapsed = time.time() - start
    check("wait rc = exit_code (0)", rc == 0, f"got: {rc}")
    check("wait блокировал (>= 1s)", elapsed >= 1.0, f"elapsed={elapsed:.2f}s")


# ============================================================================
print("\n== _builtin_kill ==")
# ============================================================================

# Запустим ДОЛГИЙ процесс и убьём его
# Используем timeout / ping -n 30 — будет работать ~30 секунд
line = "ping 127.0.0.1 -n 30 &"
toks = tokenize(line).tokens
execute_commandline(toks, raw_command=line)

time.sleep(0.5)  # дать процессу стартовать
running = [j for j in get_default_job_table().running()]
check("есть running long job", len(running) >= 1, f"got {len(running)}")

if running:
    jid = running[0].job_id
    rc = shell_utils._builtin_kill([str(jid)])
    check("kill rc=0", rc == 0, f"got: {rc}")
    time.sleep(0.5)
    check("job теперь НЕ running", not running[0].is_alive(),
          f"still alive: {running[0].is_alive()}")


# ============================================================================
print("\n== _builtin_kill -9 ==")
# ============================================================================

# Запустим ещё один и убьём через -9
line = "ping 127.0.0.1 -n 30 &"
toks = tokenize(line).tokens
execute_commandline(toks, raw_command=line)

time.sleep(0.5)
running = [j for j in get_default_job_table().running()]
if running:
    jid = running[0].job_id
    rc = shell_utils._builtin_kill(["-9", str(jid)])
    check("kill -9 rc=0", rc == 0, f"got: {rc}")


# ============================================================================
print("\n== Ошибочные случаи ==")
# ============================================================================

rc = shell_utils._builtin_kill([])
check("kill без аргументов: rc=2", rc == 2, f"got: {rc}")

rc = shell_utils._builtin_kill(["999"])
check("kill несуществующего: rc=1", rc == 1, f"got: {rc}")

rc = shell_utils._builtin_kill(["abc"])
check("kill с невалидным id: rc=2", rc == 2, f"got: {rc}")

rc = shell_utils._builtin_wait(["abc"])
check("wait с невалидным id: rc=2", rc == 2, f"got: {rc}")


print()
print("=" * 50)
print(f"  {'ALL 0.5 TESTS PASSED' if errors == 0 else f'{errors} FAILURES'}")
print("=" * 50)

sys.exit(0 if errors == 0 else 1)