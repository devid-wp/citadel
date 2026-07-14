"""
Модуль погоды для Citadel OS.

Получает текущую погоду и прогноз на несколько дней через Open-Meteo
(https://open-meteo.com) — бесплатный API без ключа.

Особенности:
  - Локация определяется автоматически по IP через system.geo.
  - Если автоматически определить не удалось — запрашивает у пользователя город/координаты.
  - Поддерживается поиск по названию города через Open-Meteo Geocoding API.
  - Погода выводится в удобной таблице с эмодзи-иконками по WMO-коду.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

import config
from core.interface import clear_screen, terminal_print, display_table, get_theme_color
from core.theme_state import get_theme_state
from rendering.draw_utils import styled_print
from system.geo import get_location, format_location

USER_AGENT = "CitadelOS/3.0 (weather)"
HTTP_TIMEOUT = 5.0


# === WMO Weather Code → русское описание + иконка ===
# Коды стандартизованы WMO, используются в Open-Meteo.
WMO_CODES = {
    0:  ("Ясно",                "☀️"),
    1:  ("Преимущественно ясно","🌤️"),
    2:  ("Переменная облачность","⛅"),
    3:  ("Пасмурно",            "☁️"),
    45: ("Туман",               "🌫️"),
    48: ("Изморозь",            "🌫️"),
    51: ("Лёгкая морось",       "🌦️"),
    53: ("Умеренная морось",    "🌦️"),
    55: ("Сильная морось",      "🌧️"),
    56: ("Ледяная морось",      "🌧️"),
    57: ("Сильная ледяная морось","🌧️"),
    61: ("Слабый дождь",        "🌦️"),
    63: ("Умеренный дождь",     "🌧️"),
    65: ("Сильный дождь",       "🌧️"),
    66: ("Ледяной дождь",       "🌧️"),
    67: ("Сильный ледяной дождь","🌧️"),
    71: ("Слабый снег",         "🌨️"),
    73: ("Умеренный снег",      "❄️"),
    75: ("Сильный снег",        "❄️"),
    77: ("Снежные зёрна",       "❄️"),
    80: ("Слабый ливень",       "🌦️"),
    81: ("Умеренный ливень",    "🌧️"),
    82: ("Сильный ливень",      "⛈️"),
    85: ("Снегопад",            "🌨️"),
    86: ("Сильный снегопад",    "❄️"),
    95: ("Гроза",               "⛈️"),
    96: ("Гроза с градом",      "⛈️"),
    99: ("Сильная гроза с градом","⛈️"),
}


def describe_wmo(code: int) -> tuple[str, str]:
    """Вернуть (описание, иконка) по WMO-коду."""
    return WMO_CODES.get(int(code), ("Неизвестно", "❓"))


def _http_get_json(url: str) -> dict | None:
    """GET → JSON, безопасный. None при любой ошибке."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError):
        return None


def geocode_city(name: str) -> dict | None:
    """Найти координаты по названию города (Open-Meteo Geocoding)."""
    name = (name or "").strip()
    if not name:
        return None
    url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode({
        "name": name,
        "count": 1,
        "language": "ru",
        "format": "json",
    })
    data = _http_get_json(url)
    if not data or not data.get("results"):
        return None
    r = data["results"][0]
    return {
        "name": r.get("name"),
        "country": r.get("country") or "",
        "admin1": r.get("admin1") or "",
        "lat": float(r.get("latitude") or 0.0),
        "lon": float(r.get("longitude") or 0.0),
    }


def fetch_weather(lat: float, lon: float) -> dict | None:
    """
    Получить текущую погоду + прогноз на 3 дня.
    Open-Meteo: возвращает hourly и daily массивы в одном запросе.
    """
    params = {
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,wind_direction_10m,pressure_msl",
        "hourly": "temperature_2m,weather_code,precipitation_probability",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
        "timezone": "auto",
        "forecast_days": 3,
    }
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
    return _http_get_json(url)


def _wind_direction(deg: float) -> str:
    """Преобразовать градусы в буквенное направление (С, СВ, В, ...)."""
    try:
        deg = float(deg)
    except (TypeError, ValueError):
        return "—"
    dirs = ["С", "СВ", "В", "ЮВ", "Ю", "ЮЗ", "З", "СЗ"]
    ix = int((deg + 22.5) // 45) % 8
    return dirs[ix]


def render_current(weather: dict, place: str) -> str:
    """Отформатировать блок 'Сейчас'."""
    cur = weather.get("current") or {}
    code = int(cur.get("weather_code") or 0)
    desc, icon = describe_wmo(code)

    temp = cur.get("temperature_2m")
    feels = cur.get("apparent_temperature")
    humid = cur.get("relative_humidity_2m")
    wind = cur.get("wind_speed_10m")
    wdir = cur.get("wind_direction_10m")
    pressure = cur.get("pressure_msl")

    def fmt(v, suffix=""):
        try:
            return f"{float(v):.1f}{suffix}"
        except (TypeError, ValueError):
            return "—"

    return (
        f"📍 {place}\n"
        f"{icon} {desc}\n"
        f"Температура: {fmt(temp)}°C (ощущается {fmt(feels)}°C)\n"
        f"Влажность: {fmt(humid)}%\n"
        f"Ветер: {fmt(wind)} км/ч {_wind_direction(wdir)}\n"
        f"Давление: {fmt(pressure)} гПа"
    )


def render_daily(weather: dict) -> list[list[str]]:
    """Сформировать строки таблицы прогноза на N дней."""
    daily = weather.get("daily") or {}
    dates = daily.get("time") or []
    codes = daily.get("weather_code") or []
    tmax = daily.get("temperature_2m_max") or []
    tmin = daily.get("temperature_2m_min") or []
    pop = daily.get("precipitation_sum") or []
    wind = daily.get("wind_speed_10m_max") or []

    rows = []
    for i, d in enumerate(dates):
        try:
            date_str = datetime.fromisoformat(d).strftime("%d.%m.%Y (%a)")
        except ValueError:
            date_str = d
        desc, icon = describe_wmo(int(codes[i] if i < len(codes) else 0))

        def f(arr, idx):
            try:
                return f"{float(arr[idx]):.1f}"
            except (IndexError, TypeError, ValueError):
                return "—"

        rows.append([
            date_str,
            f"{icon} {desc}",
            f"{f(tmin, i)} … {f(tmax, i)}°C",
            f"{f(pop, i)} мм",
            f"{f(wind, i)} км/ч",
        ])
    return rows


def render_hourly_today(weather: dict) -> list[list[str]]:
    """Сформировать строки таблицы почасового прогноза на сегодня (каждые 3 часа)."""
    hourly = weather.get("hourly") or {}
    times = hourly.get("time") or []
    codes = hourly.get("weather_code") or []
    temps = hourly.get("temperature_2m") or []
    pops = hourly.get("precipitation_probability") or []

    today = datetime.now().date().isoformat()
    rows = []
    for i, t in enumerate(times):
        if not t.startswith(today):
            continue
        try:
            hour = datetime.fromisoformat(t).strftime("%H:%M")
        except ValueError:
            hour = t
        if int(hour.split(":")[0]) % 3 != 0:
            continue

        desc, icon = describe_wmo(int(codes[i] if i < len(codes) else 0))

        def f(arr):
            try:
                return f"{float(arr[i]):.0f}"
            except (IndexError, TypeError, ValueError):
                return "—"

        rows.append([hour, f"{icon} {desc}", f"{f(temps)}°C", f"{f(pops)}%"])
    return rows


def run_weather_app():
    """Главная точка входа модуля погоды."""
    clear_screen()
    theme_color = get_theme_color()
    palette = get_theme_state().current_palette
    reset = palette.reset
    accent = palette.accent  # в DAY/EVENING=YELLOW, в NIGHT=RED

    print(f"{theme_color}=========================================")
    print("         CITADEL WEATHER ENGINE        ")
    print(f"========================================={reset}\n")

    print(f"{accent}[1]{reset} Автоматически определить моё местоположение по IP")
    print(f"{accent}[2]{reset} Ввести координаты вручную (lat, lon)")
    print(f"{accent}[3]{reset} Найти город по названию")
    print(f"{accent}[B]{reset} Назад")

    choice = input("\nВыберите режим: ").strip().lower()

    lat = lon = None
    place = ""

    if choice == "b":
        return
    elif choice == "1":
        terminal_print("[ INFO ]: Определяю ваш публичный IP-адрес...", color_code=accent)
        loc = get_location(force_refresh=True)
        if not loc:
            print(f"\n{accent}[ ERROR ]: Не удалось определить локацию. Проверьте интернет-соединение или введите данные вручную.{reset}")
            input("\nНажмите Enter для возврата...")
            return
        lat, lon = loc["lat"], loc["lon"]
        place = ", ".join(filter(None, [loc.get("city"), loc.get("country")])) or "ваше местоположение"
        print(f"\n{accent}[ OK ]{reset}  Локация определена:")
        print(format_location(loc))
    elif choice == "2":
        try:
            lat = float(input("Широта (lat): ").strip().replace(",", "."))
            lon = float(input("Долгота (lon): ").strip().replace(",", "."))
            place = f"{lat:.4f}, {lon:.4f}"
        except ValueError:
            print(f"\n{accent}[ ERROR ]: Некорректные координаты.{reset}")
            input("\nНажмите Enter для возврата...")
            return
    elif choice == "3":
        name = input("Введите название города (например, Москва): ").strip()
        terminal_print(f"[ INFO ]: Ищу '{name}'...", color_code=accent)
        g = geocode_city(name)
        if not g:
            print(f"\n{accent}[ ERROR ]: Город '{name}' не найден.{reset}")
            input("\nНажмите Enter для возврата...")
            return
        lat, lon = g["lat"], g["lon"]
        place = ", ".join(filter(None, [g.get("name"), g.get("admin1"), g.get("country")]))
    else:
        return

    print(f"\n{accent}[ INFO ]{reset}: Запрашиваю прогноз для {place}...")
    weather = fetch_weather(lat, lon)
    if not weather:
        print(f"\n{accent}[ ERROR ]: Не удалось получить погоду. Сервис недоступен.{reset}")
        input("\nНажмите Enter для возврата...")
        return

    clear_screen()
    print(f"{theme_color}=========================================")
    print("         CITADEL WEATHER — СВОДКА        ")
    print(f"========================================={reset}\n")

    terminal_print(render_current(weather, place), color_code=accent, delay=0.001)

    # Почасовой прогноз на сегодня
    hourly_rows = render_hourly_today(weather)
    if hourly_rows:
        print(f"\n{theme_color}--- ПОЧАСОВОЙ ПРОГНОЗ (СЕГОДНЯ) ---{reset}")
        display_table(["Время", "Погода", "Темп.", "Вер. осадков"], hourly_rows)

    # Прогноз на 3 дня
    daily_rows = render_daily(weather)
    if daily_rows:
        print(f"\n{theme_color}--- ПРОГНОЗ НА 3 ДНЯ ---{reset}")
        display_table(["Дата", "Погода", "Температура", "Осадки", "Ветер"], daily_rows)

    print()
    input("Нажмите Enter для возврата...")
