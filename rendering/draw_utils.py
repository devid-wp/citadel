"""
rendering/draw_utils.py
=======================

Color styling for the current environment theme.

Key functions
-------------
* apply_theme_filter(color, theme) - transforms a "raw" color according to
  the theme. Supports both input formats:
      - tuple  : (R, G, B) in 0..255 - canonical from the spec;
      - str    : key name in config.COLORS (e.g. "WHITE", "PURPLE").
* get_styled_color(name) - a high-level helper used by HUD modules.
  Pulls the current theme from ThemeState automatically.

Red-shift adaptation for Citadel
--------------------------------
The original spec says: "white -> soft red in NIGHT". In the pixel
model that is obvious: rgb(255,255,255) -> rgb(255, 80, 80).

Citadel is a TUI shell; colors are represented by ANSI codes from config.COLORS.
We CANNOT "paint" over a string like "\033[97m" - that is a different
escape. So we use a two-level model:

    logical color  ->  (R, G, B) in Citadel's logical palette
                            | apply_theme_filter()
                         (R', G', B') after the theme
                            | _ansi_for_rgb()
                         ANSI escape from config.COLORS

This lets us:
  1. honestly implement the spec's red-shift logic (we work in RGB);
  2. return an ANSI code that does not break the existing TUI rendering.

If Citadel later moves to a PIL/Pygame canvas, the lower layer
`_ansi_for_rgb` can be replaced by passing the tuple directly.
"""

from __future__ import annotations

from typing import Optional, Tuple, Union

import config

from core.theme_state import Theme, get_theme_state

ColorLike = Union[str, Tuple[int, int, int]]


# ----------------------------------------------------------------------------
# Citadel's logical palette. Name -> RGB and RGB -> ANSI mapping.
# Extensible structure: to add a new color, append to both dicts.
# ----------------------------------------------------------------------------
LOGICAL_RGB: dict[str, Tuple[int, int, int]] = {
    # Base TUI colors (approximate sRGB for logical operations).
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

# Reverse index: the "closest" ANSI from config.COLORS for a given RGB.
# (config.COLORS does not store RGB, only ANSI codes - hence the explicit mapping.)
RGB_TO_ANSI_KEY: dict[str, str] = {
    "WHITE":     "RESET",   # in TUI white = "no modifier" -> we use reset;
                            # if you have a "WHITE" color in config.COLORS -
                            # override it here.
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
    """Normalize input to (R, G, B)."""
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
    Pick the ANSI code from config.COLORS closest to the given RGB.

    Simple algorithm: choose the key from RGB_TO_ANSI_KEY with the minimal
    Euclidean distance in RGB space. Sufficient for Citadel's small
    palette (~10 colors).
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
# Red-shift parameters. Hoisted to the top so tests can swap them easily.
# ----------------------------------------------------------------------------
# Multiplier for G/B channels in NIGHT - 0.32 gives a "dark red" that
# does not "cut" the eye during long HUD reading sessions in the dark.
NIGHT_GREEN_FACTOR = 0.32
NIGHT_BLUE_FACTOR = 0.32

# Additional "warmth" - a small R boost to compensate for the brightness
# drop from the G/B multiplication. 1.0 = no change.
NIGHT_RED_BOOST = 1.00


def apply_theme_filter(
    color: ColorLike,
    theme: Optional[Union[Theme, str]] = None,
) -> Tuple[int, int, int]:
    """
    Apply the theme to a color and return the adjusted RGB.

    Parameters
    ----------
    color : (R, G, B) or logical color name
    theme : Theme / 'DAY' / 'EVENING' / 'NIGHT' / None
            If None - the current theme from ThemeState is used.

    Rules
    -----
    DAY     - no changes.
    EVENING - light "darkening" (multiply all channels by 0.85) and
              a light warm shift (R+=5, B-=5).
    NIGHT   - Red-shift per spec:
                  G *= NIGHT_GREEN_FACTOR
                  B *= NIGHT_BLUE_FACTOR
                  R *= NIGHT_RED_BOOST
              For "white" (255,255,255) -> (255, 81, 81) - soft red.
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

    # theme is Theme.NIGHT - red-shift
    return (
        min(255, int(r * NIGHT_RED_BOOST)),
        int(g * NIGHT_GREEN_FACTOR),
        int(b * NIGHT_BLUE_FACTOR),
    )


def get_styled_color(name: str) -> str:
    """
    High-level entry point for HUD modules.

        color = get_styled_color("WHITE")  -> ANSI code, ready to print

    Algorithm:
        1. Take the RGB equivalent of the logical color `name`.
        2. Apply apply_theme_filter() with the current theme.
        3. Return the ANSI code from config.COLORS.

    If `name` matches a key in config.COLORS directly (e.g. "PURPLE"),
    we still pass it through the filter so that the NIGHT shift works
    for "colored" colors as well, not only for white.
    """
    if name not in LOGICAL_RGB:
        raise KeyError(
            f"Unknown logical color '{name}'. Known: {sorted(LOGICAL_RGB)}"
        )
    rgb = apply_theme_filter(name, get_theme_state().current_theme)
    return _ansi_for_rgb(rgb)


def styled_print(text: str, color_name: str) -> None:
    """
    Convenient helper: print text in a color consistent with the theme.

    Under the hood - get_styled_color(). HUD modules should use this
    entry point instead of calling print(f"{config.COLORS[...]}")
    directly.
    """
    code = get_styled_color(color_name)
    print(f"{code}{text}{config.COLORS['RESET']}")
