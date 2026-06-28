"""
modules/clock_module.py
=======================

ClockModule — минимальный пример HUD-модуля, который АВТОМАТИЧЕСКИ
подхватывает смену темы через ThemeState, без собственного опроса времени
и без переписывания при появлении новых тем.

Демонстрирует три паттерна интеграции:
    1. Отрисовка через DrawUtils.get_styled_color() — никаких
       config.COLORS[...] напрямую.
    2. Подписка на смену темы через ThemeState.subscribe() — для
       побочных эффектов (например, обновить заголовок окна, пересчитать
       кэшированный ANSI-код).
    3. Не иметь собственного состояния «текущей темы» — всегда читать
       из ThemeState в момент отрисовки.
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Callable, Optional

from core.interface import IHUDModule
from core.theme_state import Palette, Theme, get_theme_state
from rendering.draw_utils import get_styled_color


class ClockModule(IHUDModule):
    """Часы с тематизацией под окружение."""

    name = "clock"

    def __init__(self) -> None:
        self._state = get_theme_state()
        # Снимок последней увиденной темы — полезно для отладки
        # и для модулей, у которых ДОРОГО пересчитывать цвет в render().
        self._last_theme: Theme = self._state.current_theme
        self._cached_palette: Palette = self._state.current_palette
        self._unsubscribe: Optional[Callable[[], None]] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ IHUD

    def start(self) -> None:
        # Подписка на смену темы — главный «автоматический» крючок.
        if self._unsubscribe is None:
            self._unsubscribe = self._state.subscribe(self._on_theme_changed)

    def update(self, dt: float) -> None:
        # Часы сами по себе не требуют update-логики — они «пассивны».
        # Здесь можно было бы дёргать tick(), но render() читает время
        # непосредственно при отрисовке — этого достаточно.
        return None

    def render(self, surface=None) -> None:
        """
        Отрисовка часов. Все цвета идут через get_styled_color(), поэтому
        смена темы ВЛИЯЕТ на вывод без каких-либо действий в этом методе.
        """
        now = datetime.now().strftime("%H:%M:%S")
        # Ключевая строка: ни одного прямого обращения к config.COLORS.
        # Если пользователь переключит тему через EnvAwarenessModule —
        # следующий render() автоматически отрисует часы в новом цвете.
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
        Callback подписки. Вызывается ThemeState при СМЕНЕ темы, не на
        каждый кадр. Здесь мы обновляем кэшированную палитру, чтобы
        render() не делал lookup в ThemeState на каждом вызове.
        """
        with self._lock:
            self._last_theme = new_theme
            self._cached_palette = palette
