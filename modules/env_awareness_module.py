"""
modules/env_awareness_module.py
================================

EnvAwarenessModule is an AR-HUD module responsible for the adaptive
color palette depending on the time of day.

Contract: implements core.interface.IHUDModule.

Data flow
---------
    EnvAwarenessModule  ->  ThemeState.set_theme()  ->  subscribers
                                                  |
                                                  +--> any HUD module
                                                       (via subscription
                                                        or direct poll)

Why a background thread instead of just a tick in update(dt)?
-------------------------------------------------------------
* Time of day changes slowly (about once per hour); polling every frame
  is wasteful.
* A theme boundary can fall between HUD frames; a separate daemon thread
  with period CHECK_INTERVAL guarantees that we will NOT miss a transition
  and will NOT block the main loop.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Optional

from core.interface import IHUDModule
from core.theme_state import (
    Theme,
    ThemeState,
    get_theme_state,
    theme_for_hour,
)


# Period for polling system time in the background. 60s is a compromise:
#   * less than 60s - extra load and CPU wakeups;
#   * more than 60s - we risk being up to 1 minute late on the switch,
#     which is unnoticeable to the user.
CHECK_INTERVAL = 60.0


class EnvAwarenessModule(IHUDModule):
    """
    Watches the system time and updates ThemeState.

    State is stored in ThemeState (singleton), not here - this is a
    deliberate decision: that way multiple modules can read the theme
    concurrently without locks on top of EnvAwarenessModule.
    """

    name = "env_awareness"

    def __init__(self, check_interval: float = CHECK_INTERVAL) -> None:
        self._interval = check_interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._state: ThemeState = get_theme_state()
        # Do an initial sync so ThemeState immediately reflects the real
        # time of day, not the default.
        self._state.refresh_from_clock()
        self._last_seen_theme: Theme = self._state.current_theme

    # ------------------------------------------------------------------ IHUD

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return  # idempotent start
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name=f"{self.name}-loop",
            daemon=True,  # do not block process exit
        )
        self._thread.start()

    def update(self, dt: float) -> None:
        """
        In the HUD loop: if for some reason the background thread did not
        make it in time (e.g. we are in tests without start()), pick up
        the update here. Costs almost nothing - one datetime.now() call.
        """
        self._tick(now=datetime.now())

    def render(self, surface=None) -> None:
        # EnvAwarenessModule does not draw anything itself - it is only
        # a data provider for the other modules.
        return None

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=self._interval + 1.0)
            self._thread = None

    def get_state(self) -> dict:
        return {
            "name": self.name,
            "running": self._thread is not None and self._thread.is_alive(),
            "current_theme": self._state.current_theme.value,
            "check_interval": self._interval,
        }

    # --------------------------------------------------------------- internal

    def _run(self) -> None:
        """Daemon thread loop."""
        while not self._stop_event.is_set():
            self._tick(now=datetime.now())
            # Event.wait instead of time.sleep - instant reaction to stop().
            if self._stop_event.wait(self._interval):
                break

    def _tick(self, now: datetime) -> None:
        """One step: compute the expected theme and apply it on change."""
        expected = theme_for_hour(now.hour)
        if expected is not self._last_seen_theme:
            self._last_seen_theme = expected
            self._state.set_theme(expected)
