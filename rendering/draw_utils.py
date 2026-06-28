"""
rendering/draw_utils.py
=======================

Стилизация цвета под текущую тему окружения.

Ключевые функции
----------------
* apply_theme_filter(color, theme) — преобразует «сырой» цвет с учётом
  темы. Поддерживает оба формата входа:
      - tuple  : (R, G, B) в 0..255 — канонично из ТЗ;
      - str    : имя ключа в config.COLORS (например, "WHITE", "PURPLE").
* get_styled_color(name) — высокоуровневый хелпер, которым пользуются
  модули HUD. Сам подтягивает текущую тему из ThemeState.

Адаптация Red-shift под Citadel
-------------------------------
Изначальное ТЗ говорит: «белый → мягкий красный в NIGHT». В пиксельной
модели это очевидно: rgb(255,255,255) → rgb(255, 80, 80).

Citadel — TUI-шелл, цвета представлены ANSI-кодами из config.COLORS.
Мы НЕ можем «покрасить» строку вроде "\033[97m" поверх неё — это другой
escape. Поэтому модель у нас двухуровневая:

    логический цвет  →  (R, G, B) в логической палитре Citadel
                            ↓ apply_theme_filter()
                         (R', G', B') после темы
                            ↓ _ansi_for_rgb()
                         ANSI escape из config.COLORS

Это позволяет:
  1. честно выполнить ТЗ-логику red-shift (работаем в RGB);
  2. вернуть ANSI-код, который не ломает существующую TUI-отрисовку.

Если позже Citadel переедет на PIL/Pygame-канвас, нижний слой
`_ansi_for_rgb` можно заменить на прямую передачу кортежа.
"""

from __future__ import annotations

from typing import Optional, Tuple, Union

import config

from core.theme_state import Theme, get_theme_state

ColorLike = Union[str, Tuple[int, int, int]]


# ----------------------------------------------------------------------------
# Логическая палитра Citadel. Связь имя → RGB и RGB → ANSI.
# Расширяемая структура: чтобы добавить новый цвет — дописать в оба dict.
# ----------------------------------------------------------------------------
LOGICAL_RGB: dict[str, Tuple[int, int, int]] = {
    # Базовые цвета TUI (приблизительные sRGB для логических операций).
    "WHITE":     (255, 255, 255),
    "GRAY":      (128, 128, 128),
    "RED":       (255,   0,   0),
    "GREEN":     (  0, 255,   0),
    "BLUE":      (  0,   0, 255),
    "YELLOW":    (255, 255,   0),
    "CYAN":      (  0, 255, 255),
    "MAGENTA":   (255,   0, 255),
    "PURPLE":    (180,   0, 255),
    "DARK_CYAN": (  0, 128, 128),
    "BLACK":     (  0,   0,   0),
}

# Обратный индекс: «наиболее похожий» ANSI из config.COLORS на заданный RGB.
# (config.COLORS не хранит RGB, только ANSI-коды — поэтому явный маппинг.)
RGB_TO_ANSI_KEY: dict[str, str] = {
    "WHITE":     "RESET",   # в TUI белый = «без модификатора» → возьмём сброс;
                            # если у вас есть цвет "WHITE" в config.COLORS —
                            # переопределите здесь.
    "GRAY":      "GRAY",
    "RED":       "RED",
    "GREEN":     "GREEN",
    "BLUE":      "BLUE",
    "YELLOW":    "YELLOW",
    "CYAN":      "CYAN",
    "MAGENTA":   "PURPLE",
    "PURPLE":    "PURPLE",
    "DARK_CYAN": "DARK_CYAN",
    "BLACK":     "RESET",
}


def _to_rgb(color: ColorLike) -> Tuple[int, int, int]:
    """Нормализовать вход к (R, G, B)."""
    if isinstance(color, tuple):
        if len(color) != 3:
            raise ValueError(f"RGB tuple must have 3 components, got {color}")
        return tuple(max(0, min(255, int(c))) for c in color)  # type: ignore[return-value]
    if isinstance(color, str):
        key = color.upper()
        if key not in LOGICAL_RGB:
            raise KeyError(
                f"Unknown logical color '{color}'. "
                f"Known: {sorted(LOGICAL_RGB)}"
            )
        return LOGICAL_RGB[key]
    raise TypeError(f"Unsupported color type: {type(color).__name__}")


def _ansi_for_rgb(rgb: Tuple[int, int, int]) -> str:
    """
    Подобрать ANSI-код из config.COLORS, ближайший к данному RGB.

    Простой алгоритм: выбираем ключ из RGB_TO_ANSI_KEY с минимальным
    евклидовым расстоянием в RGB-пространстве. Достаточно для маленькой
    палитры Citadel (≈10 цветов).
    """
    best_key = "RESET"
    best_dist = float("inf")
    target_r, target_g, target_b = rgb
    for logical_name, ansi_key in RGB_TO_ANSI_KEY.items():
        r, g, b = LOGICAL_RGB[logical_name]
        d = (r - target_r) ** 2 + (g - target_g) ** 2 + (b - target_b) ** 2
        if d < best_dist:
            best_dist = d
            best_key = ansi_key
    return config.COLORS.get(best_key, config.COLORS["RESET"])


# ----------------------------------------------------------------------------
# Параметры red-shift. Вынесены на верх, чтобы их легко подменить в тестах.
# ----------------------------------------------------------------------------
# Множитель для G/B каналов в NIGHT — 0.32 даёт «тёмно-красный»,
# который не «режет» глаз при длительном чтении HUD в темноте.
NIGHT_GREEN_FACTOR = 0.32
NIGHT_BLUE_FACTOR = 0.32

# Дополнительный «прогрев» — лёгкий подъём R, чтобы компенсировать
# падение яркости из-за умножения G/B. 1.0 = без изменений.
NIGHT_RED_BOOST = 1.00


def apply_theme_filter(
    color: ColorLike,
    theme: Optional[Union[Theme, str]] = None,
) -> Tuple[int, int, int]:
    """
    Применить тему к цвету и вернуть скорректированный RGB.

    Параметры
    ---------
    color : (R, G, B) или имя логического цвета
    theme : Theme / 'DAY' / 'EVENING' / 'NIGHT' / None
            Если None — используется текущая тема из ThemeState.

    Правила
    -------
    DAY     — без изменений.
    EVENING — лёгкое «затемнение» (умножение всех каналов на 0.85) и
              лёгкий сдвиг в тёплый (R+=5, B-=5).
    NIGHT   — Red-shift по ТЗ:
                  G *= NIGHT_GREEN_FACTOR
                  B *= NIGHT_BLUE_FACTOR
                  R *= NIGHT_RED_BOOST
              Для «белого» (255,255,255) → (255, 81, 81) — мягкий красный.
    """
    if theme is None:
        theme = get_theme_state().current_theme
    if isinstance(theme, str):
        theme = Theme(theme.upper())

    r, g, b = _to_rgb(color)

    if theme is Theme.DAY:
        return r, g, b

    if theme is Theme.EVENING:
        return (
            min(255, int(r * 0.85) + 5),
            int(g * 0.85),
            max(0, int(b * 0.85) - 5),
        )

    # theme is Theme.NIGHT — red-shift
    return (
        min(255, int(r * NIGHT_RED_BOOST)),
        int(g * NIGHT_GREEN_FACTOR),
        int(b * NIGHT_BLUE_FACTOR),
    )


def get_styled_color(name: str) -> str:
    """
    Высокоуровневый вход для модулей HUD.

        color = get_styled_color("WHITE")  → ANSI-код, готовый к print

    Алгоритм:
        1. Берём RGB-эквивалент логического цвета `name`.
        2. Применяем apply_theme_filter() с текущей темой.
        3. Возвращаем ANSI-код из config.COLORS.

    Если `name` совпадает с ключом в config.COLORS напрямую (например,
    "PURPLE") — мы всё равно прогоняем через фильтр, чтобы NIGHT-shift
    работал и для «цветных» цветов, а не только для белого.
    """
    if name not in LOGICAL_RGB:
        raise KeyError(
            f"Unknown logical color '{name}'. Known: {sorted(LOGICAL_RGB)}"
        )
    rgb = apply_theme_filter(name, get_theme_state().current_theme)
    return _ansi_for_rgb(rgb)


def styled_print(text: str, color_name: str) -> None:
    """
    Удобный хелпер: напечатать текст цветом, согласованным с темой.

    Под капотом — get_styled_color(). Это точка входа, на которую должны
    переходить модули HUD вместо прямых print(f"{config.COLORS[...]}").
    """
    code = get_styled_color(color_name)
    print(f"{code}{text}{config.COLORS['RESET']}")
