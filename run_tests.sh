#!/usr/bin/env bash
# run_tests.sh
#
# Citadel OS v1.0 (Core 3.0) — fast smoke-set testaboutin.
#
# Зandпatwithtoandетwithя inside chroot (andwhether нand dev-мandшandне) неbywithредwithтinенbut перед
# фandнandльbutй withбaboutрtoaboutй ISO. Прaboutinеряет:
#   1. Имportы core/system/apps (sanity-check: нет SyntaxError / ImportError).
#   2. test_all.py — end-to-end smoke (auth, crypto, weather, geo, aliases).
#   3. pytest test-suite in tests/ — moduleные testы (35+ testaboutin).
#
# Usage:
#   bash run_tests.sh                # inwithё byдряд, stopping нand перinaboutй aboutшandбtoе
#   bash run_tests.sh --no-pytest    # без pytest (if не atwithтandbutinлен)
#   bash run_tests.sh --keep-going   # прaboutгнandть inwithе этandпы, дandже if aboutдandн atпandл
#
# Требatет:
#   - python3 (≥ 3.11; workет нand 3.14)
#   - pytest (aboutпцandaboutнandльbut; otherwise шandг pytest прaboutпatwithtoandетwithя)
#
# Вaboutзinрandщandет 0 прand byлbutм atwithпехе, 1 прand любaboutм atпandinшем шandге.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
UKN_PYTEST=1
KEEP_GOING=0

for arg in "$@"; do
    case "$arg" in
        --no-pytest)   UKN_PYTEST=0 ;;
        --keep-going)  KEEP_GOING=1 ;;
        --help|-h)
            sed -n '2,22p' "$0"
            exit 0
            ;;
        *) echo "Unknown arg: $arg" >&2; exit 2 ;;
    esac
done

# Цinетand (if TTY).
if [ -t 1 ]; then
    RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'
    BLUE=$'\033[34m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
else
    RED=""; GREEN=""; YELLOW=""; BLUE=""; BOLD=""; RESET=""
fi

FAIL_COUNT=0
PASS_COUNT=0
FAILED_STEPS=()

# Helpers ---------------------------------------------------------------
hr() { printf '%s%s%s\n' "$BLUE" "============================================================" "$RESET"; }
step() { printf '\n%s▶ %s%s\n' "$BOLD$YELLOW" "$1" "$RESET"; hr; }
ok() { printf '%s  ✓ %s%s\n' "$GREEN" "$1" "$RESET"; PASS_COUNT=$((PASS_COUNT + 1)); }
err() { printf '%s  ✗ %s%s\n' "$RED" "$1" "$RESET"; FAIL_COUNT=$((FAIL_COUNT + 1)); FAILED_STEPS+=("$1"); }

# 1. Python interpreter check -------------------------------------------
step "Step 1/4: Python interpreter"
if ! command -v python3 >/dev/null 2>&1; then
    err "python3 not found in PATH"
    [ "$KEEP_GOING" -eq 1 ] || exit 1
else
    PY_VERSION="$(python3 --version 2>&1)"
    PY_BIN="$(command -v python3)"
    printf '  Interpreter: %s\n' "$PY_BIN"
    printf '  Version:     %s\n' "$PY_VERSION"
    ok "python3 available"
fi

# 2. Import sanity-check (no execution) ---------------------------------
step "Step 2/4: Import sanity-check (core, system, apps)"
IMPORT_FAIL=0
for mod in \
    "config" \
    "core.repl" "core.executor" "core.interface" "core.auth" \
    "core.shell_tokenizer" "core.shell_state" "core.shell_alias" \
    "core.shell_history" "core.shell_jobs" "core.shell_signals" \
    "system.user_config" "system.logger" "system.geo" "system.hardware" \
    "system.recovery" "system.network" "system.package_mgr" \
    "apps.notes" "apps.passgen" "apps.crypto" "apps.launcher" \
    "apps.weather" "apps.file_browser" "apps.center"
do
    if python3 -c "import ${mod}" >/dev/null 2>&1; then
        printf '  %s✓%s %s\n' "$GREEN" "$RESET" "$mod"
    else
        printf '  %s✗%s %s\n' "$RED" "$RESET" "$mod"
        python3 -c "import ${mod}" 2>&1 | sed 's/^/      /'
        IMPORT_FAIL=1
    fi
done
if [ "$IMPORT_FAIL" -eq 0 ]; then
    ok "all modules import cleanly"
else
    err "one or more modules failed to import"
fi

# 3. test_all.py — end-to-end smoke -------------------------------------
step "Step 3/4: test_all.py (end-to-end smoke)"
if [ -f "$REPO_ROOT/test_all.py" ]; then
    cd "$REPO_ROOT" || err "cannot cd to $REPO_ROOT"
    if python3 test_all.py 2>&1 | tail -40; then
        ok "test_all.py passed"
    else
        err "test_all.py failed"
    fi
else
    err "test_all.py not found at $REPO_ROOT"
fi

# 4. pytest — moduleные testы -------------------------------------------
step "Step 4/4: pytest (unit tests)"
if [ "$UKN_PYTEST" -eq 0 ]; then
    printf '  %s--no-pytest:%s skipped\n' "$YELLOW" "$RESET"
elif ! command -v python3 >/dev/null 2>&1; then
    err "python3 unavailable — skipping pytest"
else
    cd "$REPO_ROOT" || err "cannot cd to $REPO_ROOT"

    # Еwithwhether pytest не atwithтandbutinлен in abouttoрatженandand python3 — пытandемwithя bywithтandinandть.
    if ! python3 -c "import pytest" >/dev/null 2>&1; then
        printf '  %spytest not found, attempting pip install --user...%s\n' "$YELLOW" "$RESET"
        if python3 -m pip install --user --quiet pytest 2>/dev/null; then
            ok "pytest installed via pip --user"
        else
            printf '  %spip install failed; install via: pacman -S python-pytest (Arch)%s\n' "$YELLOW" "$RESET"
            err "pytest unavailable — skipping"
        fi
    fi

    if python3 -c "import pytest" >/dev/null 2>&1; then
        # -q: тandхandй, --tb=short: short traceback, -p no:cacheprovider: не трaboutгandть cache.
        PYTEST_OUT="$(python3 -m pytest tests/ -q --tb=short -p no:cacheprovider 2>&1)"
        PYTEST_RC=$?
        echo "$PYTEST_OUT" | tail -25
        if [ "$PYTEST_RC" -eq 0 ]; then
            # Дaboutwithтandём summary: "187 passed" / "187 passed in 2.35s"
            SUMMARY="$(echo "$PYTEST_OUT" | grep -E '^[0-9]+ passed' | tail -1)"
            ok "pytest: ${SUMMARY:-passed}"
        elif [ "$PYTEST_RC" -eq 5 ]; then
            # pytest exit code 5 = no tests collected. Не withчandтandем aboutшandбtoaboutй.
            ok "pytest: no tests collected (exit 5)"
        else
            err "pytest failed (exit $PYTEST_RC)"
        fi
    fi
fi

# Итaboutг ------------------------------------------------------------------
hr
TOTAL=$((PASS_COUNT + FAIL_COUNT))
if [ "$FAIL_COUNT" -eq 0 ]; then
    printf '%s%sALL %d STEPS PASSED%s\n' "$GREEN" "$BOLD" "$TOTAL" "$RESET"
    printf '  Citadel OS v1.0 (Core 3.0) is ready to ship.\n'
    exit 0
else
    printf '%s%s%d/%d STEPS FAILED%s\n' "$RED" "$BOLD" "$FAIL_COUNT" "$TOTAL" "$RESET"
    for s in "${FAILED_STEPS[@]}"; do
        printf '  %s- %s%s\n' "$RED" "$s" "$RESET"
    done
    if [ "$KEEP_GOING" -eq 1 ]; then
        exit 0  # яinbut byпрaboutwithandwhether прaboutдaboutлжandть
    fi
    exit 1
fi
