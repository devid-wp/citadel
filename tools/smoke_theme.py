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
    _hr("Сценарий 1: тема по часу суток")
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
    _hr("Сценарий 2: Red-shift белого в NIGHT")
    reset_theme_state_for_tests()
    state = get_theme_state()

    # DAY — без изменений
    state.set_theme(Theme.DAY)
    white_day = apply_theme_filter((255, 255, 255), Theme.DAY)
    print(f"DAY  white → {white_day}")

    # EVENING — лёгкое затемнение + тёплый сдвиг
    state.set_theme(Theme.EVENING)
    white_eve = apply_theme_filter((255, 255, 255), Theme.EVENING)
    print(f"EVE  white → {white_eve}")

    # NIGHT — red-shift (ТЗ: белый → мягкий красный)
    state.set_theme(Theme.NIGHT)
    white_night = apply_theme_filter((255, 255, 255), Theme.NIGHT)
    print(f"NIGHT white → {white_night}")
    # Ожидаемо: G≈81, B≈81, R=255
    assert white_night[0] == 255, "Red channel must stay max"
    assert white_night[1] <= 100, f"Green must be reduced, got {white_night[1]}"
    assert white_night[2] <= 100, f"Blue must be reduced, got {white_night[2]}"
    print("  red-shift OK (G,B ≤ 100)")


def scenario_render_output() -> None:
    _hr("Сценарий 3: get_styled_color() под каждой темой")
    reset_theme_state_for_tests()
    state = get_theme_state()
    for theme in (Theme.DAY, Theme.EVENING, Theme.NIGHT):
        state.set_theme(theme)
        print(f"-- {theme.value} --")
        # Логический цвет WHITE, разные темы → разные ANSI-коды
        ansi = get_styled_color("WHITE")
        print(f"  WHITE  → {ansi!r} (bytes={ansi.encode()!r})")
        styled_print("Цифровые часы HUD активны.", "WHITE")


def scenario_concurrent() -> None:
    _hr("Сценарий 4: потокобезопасность (100 переключений из 4 потоков)")
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
    print(f"  получено уведомлений: {len(received)}")
    assert len(received) > 0, "subscribers should have been notified"
    print(f"  первое уведомление: {received[0].value}")
    print(f"  последнее:          {received[-1].value}")


def scenario_live_module() -> None:
    _hr("Сценарий 5: живой модуль EnvAwarenessModule + ClockModule")
    reset_theme_state_for_tests()
    env = EnvAwarenessModule(check_interval=0.2)
    clock = ClockModule()
    env.start()
    clock.start()

    print(f"  now={datetime.now().strftime('%H:%M:%S')}")
    print(f"  текущая тема: {get_theme_state().current_theme.value}")
    clock.render()

    # Симулируем «прыжок во времени» через прямой вызов API
    state = get_theme_state()
    print("\n  форсируем тему NIGHT (имитация 23:00):")
    state.set_theme(Theme.NIGHT)
    time.sleep(0.05)
    clock.render()

    print("\n  форсируем тему EVENING (имитация 19:00):")
    state.set_theme(Theme.EVENING)
    time.sleep(0.05)
    clock.render()

    env.stop()
    clock.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test for theme system")
    parser.add_argument("--hour", type=int, help="Проверить конкретный час (0..23)")
    parser.add_argument("--concurrent", action="store_true",
                        help="Только сценарий потокобезопасности")
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
    print("\n[ OK ] все сценарии прошли.\n")


if __name__ == "__main__":
    main()
