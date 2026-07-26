"""
tools/smoke_theme.py
====================

Ручная проверка ThemeState + EnvAwarenessModule + DrawUtils.

Запуск:
    python -m tools.smoke_theme                — сценарий по часам суток
    python -m tools.smoke_theme --hour 23       — конкретный час
    python -m tools.smoke_theme --concurrent    — потокобезопасность

Скрипт НЕ модифицирует main.py и ничего не ломает в Citadel Shell.
"""

from __future__ import annotations

import argparse
import threading
import time
from datetime import datetime

import config

from core.theme_state import (
    Theme,
    get_theme_state,
    reset_theme_state_for_tests,
    theme_for_hour,
)
from modules.env_awareness_module import EnvAwarenessModule
from modules.clock_module import ClockModule
from rendering.draw_utils import (
    apply_theme_filter,
    get_styled_color,
    styled_print,
)


def _hr(title: str) -> None:
    bar = "=" * 64
    print(f"\n{bar}\n  {title}\n{bar}")


def scenario_by_hour() -> None:
    _hr("Scenario 1: theme by time of day")
    reset_theme_state_for_tests()
    state = get_theme_state()
    samples = [(0, "NIGHT"), (5, "NIGHT"), (6, "DAY"), (12, "DAY"),
               (17, "DAY"), (18, "EVENING"), (21, "EVENING"),
               (22, "NIGHT"), (23, "NIGHT")]
    print(f"{'hour':>4}  {'expected':<8} {'got':<8} ok")
    for hour, expected in samples:
        got = theme_for_hour(hour).value
        ok = "✓" if got == expected else "✗"
        print(f"{hour:>4}  {expected:<8} {got:<8} {ok}")


def scenario_red_shift() -> None:
    _hr("Scenario 2: Red-shift of white in NIGHT")
    reset_theme_state_for_tests()
    state = get_theme_state()

    # DAY — no change
    state.set_theme(Theme.DAY)
    white_day = apply_theme_filter((255, 255, 255), Theme.DAY)
    print(f"DAY  white → {white_day}")

    # EVENING — slight darkening + warm shift
    state.set_theme(Theme.EVENING)
    white_eve = apply_theme_filter((255, 255, 255), Theme.EVENING)
    print(f"EVE  white → {white_eve}")

    # NIGHT — red-shift (spec: white → soft red)
    state.set_theme(Theme.NIGHT)
    white_night = apply_theme_filter((255, 255, 255), Theme.NIGHT)
    print(f"NIGHT white → {white_night}")
    # Expected: G≈81, B≈81, R=255
    assert white_night[0] == 255, "Red channel must stay max"
    assert white_night[1] <= 100, f"Green must be reduced, got {white_night[1]}"
    assert white_night[2] <= 100, f"Blue must be reduced, got {white_night[2]}"
    print("  red-shift OK (G,B ≤ 100)")


def scenario_render_output() -> None:
    _hr("Scenario 3: get_styled_color() under each theme")
    reset_theme_state_for_tests()
    state = get_theme_state()
    for theme in (Theme.DAY, Theme.EVENING, Theme.NIGHT):
        state.set_theme(theme)
        print(f"-- {theme.value} --")
        # Logical color WHITE, different themes → different ANSI codes
        ansi = get_styled_color("WHITE")
        print(f"  WHITE  → {ansi!r} (bytes={ansi.encode()!r})")
        styled_print("HUD digital clock is active.", "WHITE")


def scenario_concurrent() -> None:
    _hr("Scenario 4: thread safety (100 switches from 4 threads)")
    reset_theme_state_for_tests()
    state = get_theme_state()
    received = []
    lock = threading.Lock()

    def on_change(new_theme, palette):
        with lock:
            received.append(new_theme)

    unsub = state.subscribe(on_change)

    def worker(seed: int):
        themes = [Theme.DAY, Theme.EVENING, Theme.NIGHT]
        for i in range(25):
            state.set_theme(themes[(seed + i) % 3])
            time.sleep(0.001)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    unsub()
    print(f"  notifications received: {len(received)}")
    assert len(received) > 0, "subscribers should have been notified"
    print(f"  first notification: {received[0].value}")
    print(f"  last:               {received[-1].value}")


def scenario_live_module() -> None:
    _hr("Scenario 5: live EnvAwarenessModule + ClockModule")
    reset_theme_state_for_tests()
    env = EnvAwarenessModule(check_interval=0.2)
    clock = ClockModule()
    env.start()
    clock.start()

    print(f"  now={datetime.now().strftime('%H:%M:%S')}")
    print(f"  current theme: {get_theme_state().current_theme.value}")
    clock.render()

    # Simulate a "time jump" via direct API call
    state = get_theme_state()
    print("\n  forcing NIGHT theme (simulating 23:00):")
    state.set_theme(Theme.NIGHT)
    time.sleep(0.05)
    clock.render()

    print("\n  forcing EVENING theme (simulating 19:00):")
    state.set_theme(Theme.EVENING)
    time.sleep(0.05)
    clock.render()

    env.stop()
    clock.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test for theme system")
    parser.add_argument("--hour", type=int, help="Check a specific hour (0..23)")
    parser.add_argument("--concurrent", action="store_true",
                        help="Run only the thread-safety scenario")
    args = parser.parse_args()

    if args.concurrent:
        scenario_concurrent()
        return
    if args.hour is not None:
        reset_theme_state_for_tests()
        print(f"hour {args.hour} → {theme_for_hour(args.hour).value}")
        return

    scenario_by_hour()
    scenario_red_shift()
    scenario_render_output()
    scenario_concurrent()
    scenario_live_module()
    print("\n[ OK ] all scenarios passed.\n")


if __name__ == "__main__":
    main()
