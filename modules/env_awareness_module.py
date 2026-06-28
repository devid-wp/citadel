"""
modules/env_awareness_module.py
================================

EnvAwarenessModule — модуль AR-HUD, отвечающий за адаптивную цветовую
палитру в зависимости от времени суток.

Контракт: реализует core.interface.IHUDModule.

Поток данных
------------
    EnvAwarenessModule  ─►  ThemeState.set_theme()  ─►  subscribers
                                                  │
                                                  └─►  любой модуль HUD
                                                       (через подписку
                                                        или прямой опрос)

Почему фоновый поток, а не просто tick в update(dt)?
-----------------------------------------------------
* Время суток меняется медленно (раз в час), опрашивать каждый кадр —
  расточительно.
* Граница темы может наступить между кадрами HUD; отдельный daemon-поток
  с периодом CHECK_INTERVAL гарантирует, что мы НЕ пропустим переход и
  НЕ будем блокировать основной цикл.
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


# Период опроса системного времени в фоне. 60с — компромисс:
#   * меньше 60с — лишняя нагрузка и пробуждения CPU;
#   * больше 60с — мы рискуем опоздать с переключением на 1 минуту,
#     что незаметно пользователю.
CHECK_INTERVAL = 60.0


class EnvAwarenessModule(IHUDModule):
    """
    Следит за системным временем и обновляет ThemeState.

    Состояние хранится в ThemeState (singleton), а не здесь — это
    сознательное решение: так несколько модулей могут одновременно
    читать тему без блокировок поверх EnvAwarenessModule.
    """

    name = "env_awareness"

    def __init__(self, check_interval: float = CHECK_INTERVAL) -> None:
        self._interval = check_interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._state: ThemeState = get_theme_state()
        # Сделать первичную синхронизацию, чтобы ThemeState сразу
        # отражал реальное время суток, а не дефолтное.
        self._state.refresh_from_clock()
        self._last_seen_theme: Theme = self._state.current_theme

    # ------------------------------------------------------------------ IHUD

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return  # идемпотентный start
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name=f"{self.name}-loop",
            daemon=True,  # не блокируем выход процесса
        )
        self._thread.start()

    def update(self, dt: float) -> None:
        """
        В HUD-цикле: если фоновый поток по какой-то причине не успел
        (например, мы в тестах без start()), подхватим обновление здесь.
        Стоит копейки — один вызов datetime.now().
        """
        self._tick(now=datetime.now())

    def render(self, surface=None) -> None:
        # EnvAwarenessModule ничего не рисует сам — он только поставщик
        # данных для остальных модулей.
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
        """Цикл daemon-потока."""
        while not self._stop_event.is_set():
            self._tick(now=datetime.now())
            # Event.wait вместо time.sleep — мгновенная реакция на stop().
            if self._stop_event.wait(self._interval):
                break

    def _tick(self, now: datetime) -> None:
        """Один шаг: вычислить ожидаемую тему и применить при изменении."""
        expected = theme_for_hour(now.hour)
        if expected is not self._last_seen_theme:
            self._last_seen_theme = expected
            self._state.set_theme(expected)
