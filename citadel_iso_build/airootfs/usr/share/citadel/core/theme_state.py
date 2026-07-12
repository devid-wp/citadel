"""
core/theme_state.py
===================

Потокобезопасный singleton, хранящий текущую «тему окружения» (DAY / EVENING
/ NIGHT) для AR-HUD подсистемы Citadel.

Зачем singleton + threading.Lock
---------------------------------
* К теме одновременно обращаются:
  - фоновый поток EnvAwarenessModule (обновляет),
  - основной цикл HUD (читает каждый кадр),
  - любой модуль (ClockModule, SpeedModule, ...) при отрисовке.
* Без синхронизации возможны «грязные» чтения (частично записанный
  Enum-объект в CPython невозможен из-за GIL, но у нас обычные строки,
  поэтому Lock всё равно обязателен).

Паттерн подписки
----------------
Любой код может зарегистрировать callback, который будет вызван при СМЕНЕ
темы. Это и есть «крючок», через который остальные модули узнают о новой
теме без явной передачи им команды. Подробнее — см. README/ARCHITECTURE.md.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable, List, Optional

import config


class Theme(Enum):
    DAY = "DAY"
    EVENING = "EVENING"
    NIGHT = "NIGHT"


# ----------------------------------------------------------------------------
# Правила перехода «время суток → тема». Вынесены в одно место, чтобы
# тесты могли их подменить (см. tools/smoke_theme.py).
# ----------------------------------------------------------------------------
#   DAY     : 06:00 .. 17:59
#   EVENING : 18:00 .. 21:59
#   NIGHT   : 22:00 .. 05:59  (через границу полуночи)
THEME_BOUNDARIES = {
    Theme.DAY: (6, 18),
    Theme.EVENING: (18, 22),
    # NIGHT — особый случай: вне диапазонов DAY/EVENING
}


def theme_for_hour(hour: int) -> Theme:
    """Чистая функция: час 0..23 → Theme."""
    if not 0 <= hour <= 23:
        raise ValueError(f"hour must be 0..23, got {hour}")
    if 6 <= hour < 18:
        return Theme.DAY
    if 18 <= hour < 22:
        return Theme.EVENING
    return Theme.NIGHT


# ----------------------------------------------------------------------------
# Метаданные темы: маппинг Theme → основной ANSI-цвет Citadel из config.COLORS.
# Это позволяет ThemeState быть единственным источником правды о «цвете
# настроения» — остальные модули просто спрашивают current_palette().
# ----------------------------------------------------------------------------
THEME_PRIMARY_COLOR = {
    Theme.DAY: "CYAN",        # спокойный, нейтрально-дневной
    Theme.EVENING: "PURPLE",  # тёплый закат (текущий default Citadel)
    Theme.NIGHT: "DARK_CYAN", # приглушённый ночной
}


@dataclass(frozen=True)
class Palette:
    """Палитра для одной темы. frozen=True → immutable, безопасно шарить."""
    theme: Theme
    primary: str         # ANSI-код основного цвета (из config.COLORS)
    accent: str          # ANSI-код акцента
    muted: str           # ANSI-код приглушённого/служебного текста
    reset: str           # ANSI-код сброса (обычно config.COLORS["RESET"])

    @classmethod
    def for_theme(cls, theme: Theme) -> "Palette":
        cols = config.COLORS
        return cls(
            theme=theme,
            primary=cols.get(THEME_PRIMARY_COLOR[theme], cols["PURPLE"]),
            accent=cols["YELLOW"] if theme is not Theme.NIGHT else cols["RED"],
            muted=cols["GRAY"],
            reset=cols["RESET"],
        )


class ThemeState:
    """
    Singleton с потокобезопасным доступом. Хранит текущую Theme + Palette,
    умеет уведомлять подписчиков о смене.

    Потокобезопасность:
        * __init__ защищён class-level Lock (double-checked init).
        * set_theme() берёт self._lock на запись и notify.
        * current_*() читают под self._lock.
    """

    _instance: Optional["ThemeState"] = None
    _init_lock = threading.Lock()

    def __new__(cls) -> "ThemeState":
        # Double-checked locking — дешёвая инициализация под GIL.
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        # __init__ вызывается на каждом ThemeState() — защищаемся флагом.
        if getattr(self, "_initialized", False):
            return
        self._lock = threading.RLock()
        self._theme: Theme = theme_for_hour(datetime.now().hour)
        self._palette: Palette = Palette.for_theme(self._theme)
        self._subscribers: List[Callable[[Theme, Palette], None]] = []
        self._initialized = True

    # ------------------------------------------------------------------ API

    @property
    def current_theme(self) -> Theme:
        with self._lock:
            return self._theme

    @property
    def current_palette(self) -> Palette:
        with self._lock:
            return self._palette

    def set_theme(self, new_theme: Theme, *, force_notify: bool = False) -> bool:
        """
        Сменить тему. Возвращает True, если тема реально изменилась
        (или если force_notify=True). Подписчики вызываются ВСЕГДА при
        force_notify и ТОЛЬКО при реальной смене иначе.
        """
        with self._lock:
            changed = (new_theme is not self._theme) or force_notify
            self._theme = new_theme
            self._palette = Palette.for_theme(new_theme)
            subs = list(self._subscribers)  # snapshot под локом
        if changed:
            for cb in subs:
                try:
                    cb(new_theme, self._palette)
                except Exception as exc:  # noqa: BLE001
                    # Подписчик не должен валить весь pipeline.
                    # Логируем в stderr, чтобы не зависеть от system.logger
                    # (ThemeState — низкоуровневый модуль).
                    import sys
                    print(f"[ThemeState] subscriber error: {exc}", file=sys.stderr)
        return changed

    def refresh_from_clock(self, now: Optional[datetime] = None) -> bool:
        """
        Удобный хелпер: взять текущий час и применить соответствующую тему.
        Возвращает True при реальной смене.
        """
        now = now or datetime.now()
        return self.set_theme(theme_for_hour(now.hour))

    def subscribe(self, callback: Callable[[Theme, Palette], None]) -> Callable[[], None]:
        """
        Подписаться на смену темы. Возвращает функцию отписки (idempotent).
        Это и есть «крючок», через который остальные модули узнают о новой
        теме без опроса.
        """
        with self._lock:
            self._subscribers.append(callback)
        def _unsubscribe() -> None:
            with self._lock:
                if callback in self._subscribers:
                    self._subscribers.remove(callback)
        return _unsubscribe


# ----------------------------------------------------------------------------
# Module-level singleton accessor. Импортирующий код пишет:
#     from core.theme_state import get_theme_state
#     get_theme_state().current_theme
# Это устойчиво к circular import и monkey-patching в тестах.
# ----------------------------------------------------------------------------

def get_theme_state() -> ThemeState:
    return ThemeState()


def reset_theme_state_for_tests() -> None:
    """
    Сброс singleton для тестов. В проде НЕ вызывать — есть подписчики,
    которых мы не очищаем здесь (тесты и так работают с одним набором).
    """
    with ThemeState._init_lock:
        ThemeState._instance = None
