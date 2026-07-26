"""
modules/clock_module.py
=======================

ClockModule is a minimal example of a HUD module that AUTOMATICALLY
picks up theme changes via ThemeState, without its own time polling
and without rewriting when new themes appear.

It demonstrates three integration patterns:
    1. Rendering via DrawUtils.get_styled_color() - no direct
       config.COLORS[...] access.
    2. Subscribing to theme changes via ThemeState.subscribe() - for
       side effects (e.g. update the window title, recompute a
       cached ANSI code).
    3. Do not keep your own "current theme" state - always read from
       ThemeState at the moment of rendering.
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Callable, Optional

from core.interface import IHUDModule
from core.theme_state import Palette, Theme, get_theme_state
from rendering.draw_utils import get_styled_color


class ClockModule(IHUDModule):
    """A clock themed to the surrounding environment."""

    name = "clock"

    def __init__(self) -> None:
        self._state = get_theme_state()
        # Snapshot of the last seen theme - useful for debugging
        # and for modules where it is EXPENSIVE to recompute the color in render().
        self._last_theme: Theme = self._state.current_theme
        self._cached_palette: Palette = self._state.current_palette
        self._unsubscribe: Optional[Callable[[], None]] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ IHUD

    def start(self) -> None:
        # Subscription to theme changes - the main "automatic" hook.
        if self._unsubscribe is None:
            self._unsubscribe = self._state.subscribe(self._on_theme_changed)

    def update(self, dt: float) -> None:
        # The clock itself does not require update logic - it is "passive".
        # We could call tick() here, but render() reads the time
        # directly at render time - that is enough.
        return None

    def render(self, surface=None) -> None:
        """
        Render the clock. All colors go through get_styled_color(), so a
        theme change AFFECTS the output without any action inside this method.
        """
        now = datetime.now().strftime("%H:%M:%S")
        # Key line: not a single direct access to config.COLORS.
        # If the user switches the theme via EnvAwarenessModule -
        # the next render() will automatically render the clock in the new color.
        color = get_styled_color("WHITE")
        reset = self._cached_palette.reset
        print(f"  {color}[CLOCK]{reset} {now}")

    def stop(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    def get_state(self) -> dict:
        return {
            "name": self.name,
            "running": self._unsubscribe is not None,
            "current_theme": self._last_theme.value,
        }

    # --------------------------------------------------------------- internal

    def _on_theme_changed(self, new_theme: Theme, palette: Palette) -> None:
        """
        Subscription callback. Called by ThemeState on a theme CHANGE, not
        every frame. Here we update the cached palette so that render()
        does not look up ThemeState on every call.
        """
        with self._lock:
            self._last_theme = new_theme
            self._cached_palette = palette
