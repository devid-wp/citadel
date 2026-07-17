"""
Weather module for Citadel OS.

Fetches the current weather and a multi-day forecast from Open-Meteo
(https://open-meteo.com) — a free, no-key API.

Features:
  - Automatic location detection by IP via system.geo.
  - If automatic detection fails — prompts the user for a city / coordinates.
  - City search by name via the Open-Meteo Geocoding API.
  - Weather is rendered as a tidy table with emoji icons by WMO code.
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


# === WMO Weather Code → English description + icon ===
# Codes are standardized by the WMO and used by Open-Meteo.
WMO_CODES = {
    0:  ("Clear sky",                "☀️"),
    1:  ("Mainly clear",             "🌤️"),
    2:  ("Partly cloudy",            "⛅"),
    3:  ("Overcast",                 "☁️"),
    45: ("Fog",                      "🌫️"),
    48: ("Depositing rime fog",      "🌫️"),
    51: ("Light drizzle",            "🌦️"),
    53: ("Moderate drizzle",         "🌦️"),
    55: ("Dense drizzle",            "🌧️"),
    56: ("Light freezing drizzle",   "🌧️"),
    57: ("Dense freezing drizzle",   "🌧️"),
    61: ("Light rain",               "🌦️"),
    63: ("Moderate rain",            "🌧️"),
    65: ("Heavy rain",               "🌧️"),
    66: ("Light freezing rain",      "🌧️"),
    67: ("Heavy freezing rain",      "🌧️"),
    71: ("Light snow",               "🌨️"),
    73: ("Moderate snow",            "❄️"),
    75: ("Heavy snow",               "❄️"),
    77: ("Snow grains",              "❄️"),
    80: ("Light rain showers",       "🌦️"),
    81: ("Moderate rain showers",    "🌧️"),
    82: ("Violent rain showers",     "⛈️"),
    85: ("Snow showers",             "🌨️"),
    86: ("Heavy snow showers",       "❄️"),
    95: ("Thunderstorm",             "⛈️"),
    96: ("Thunderstorm with hail",   "⛈️"),
    99: ("Severe thunderstorm with hail", "⛈️"),
}


def describe_wmo(code: int) -> tuple[str, str]:
    """Return (description, icon) for a WMO code."""
    return WMO_CODES.get(int(code), ("Unknown", "❓"))


def _http_get_json(url: str) -> dict | None:
    """Safe GET → JSON. Returns None on any error."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError):
        return None


def geocode_city(name: str) -> dict | None:
    """Look up coordinates by city name (Open-Meteo Geocoding)."""
    name = (name or "").strip()
    if not name:
        return None
    url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode({
        "name": name,
        "count": 1,
        "language": "en",
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
    Fetch the current weather + 3-day forecast.
    Open-Meteo: returns hourly and daily arrays in a single request.
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
    """Convert a degree value to a cardinal direction letter (N, NE, E, ...)."""
    try:
        deg = float(deg)
    except (TypeError, ValueError):
        return "—"
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    ix = int((deg + 22.5) // 45) % 8
    return dirs[ix]


def render_current(weather: dict, place: str) -> str:
    """Format the 'Now' block."""
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
        f"Temperature: {fmt(temp)}°C (feels like {fmt(feels)}°C)\n"
        f"Humidity: {fmt(humid)}%\n"
        f"Wind: {fmt(wind)} km/h {_wind_direction(wdir)}\n"
        f"Pressure: {fmt(pressure)} hPa"
    )


def render_daily(weather: dict) -> list[list[str]]:
    """Build rows for the N-day forecast table."""
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
            f"{f(pop, i)} mm",
            f"{f(wind, i)} km/h",
        ])
    return rows


def render_hourly_today(weather: dict) -> list[list[str]]:
    """Build rows for today's hourly forecast (every 3 hours)."""
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
    """Main entry point of the weather module."""
    clear_screen()
    theme_color = get_theme_color()
    palette = get_theme_state().current_palette
    reset = palette.reset
    accent = palette.accent  # in DAY/EVENING=YELLOW, in NIGHT=RED

    print(f"{theme_color}=========================================")
    print("         CITADEL WEATHER ENGINE        ")
    print(f"========================================={reset}\n")

    print(f"{accent}[1]{reset} Detect my location automatically by IP")
    print(f"{accent}[2]{reset} Enter coordinates manually (lat, lon)")
    print(f"{accent}[3]{reset} Find a city by name")
    print(f"{accent}[B]{reset} Back")

    choice = input("\nSelect a mode: ").strip().lower()

    lat = lon = None
    place = ""

    if choice == "b":
        return
    elif choice == "1":
        terminal_print("[ INFO ]: Detecting your public IP address...", color_code=accent)
        loc = get_location(force_refresh=True)
        if not loc:
            print(f"\n{accent}[ ERROR ]: Could not determine location. Check your internet connection or enter data manually.{reset}")
            input("\nPress Enter to return...")
            return
        lat, lon = loc["lat"], loc["lon"]
        place = ", ".join(filter(None, [loc.get("city"), loc.get("country")])) or "your location"
        print(f"\n{accent}[ OK ]{reset}  Location detected:")
        print(format_location(loc))
    elif choice == "2":
        try:
            lat = float(input("Latitude (lat): ").strip().replace(",", "."))
            lon = float(input("Longitude (lon): ").strip().replace(",", "."))
            place = f"{lat:.4f}, {lon:.4f}"
        except ValueError:
            print(f"\n{accent}[ ERROR ]: Invalid coordinates.{reset}")
            input("\nPress Enter to return...")
            return
    elif choice == "3":
        name = input("Enter city name (e.g. London): ").strip()
        terminal_print(f"[ INFO ]: Looking up '{name}'...", color_code=accent)
        g = geocode_city(name)
        if not g:
            print(f"\n{accent}[ ERROR ]: City '{name}' not found.{reset}")
            input("\nPress Enter to return...")
            return
        lat, lon = g["lat"], g["lon"]
        place = ", ".join(filter(None, [g.get("name"), g.get("admin1"), g.get("country")]))
    else:
        return

    print(f"\n{accent}[ INFO ]{reset}: Requesting forecast for {place}...")
    weather = fetch_weather(lat, lon)
    if not weather:
        print(f"\n{accent}[ ERROR ]: Failed to retrieve weather. The service is unavailable.{reset}")
        input("\nPress Enter to return...")
        return

    clear_screen()
    print(f"{theme_color}=========================================")
    print("         CITADEL WEATHER — OVERVIEW        ")
    print(f"========================================={reset}\n")

    terminal_print(render_current(weather, place), color_code=accent, delay=0.001)

    # Hourly forecast for today
    hourly_rows = render_hourly_today(weather)
    if hourly_rows:
        print(f"\n{theme_color}--- HOURLY FORECAST (TODAY) ---{reset}")
        display_table(["Time", "Weather", "Temp.", "Precip. prob."], hourly_rows)

    # 3-day forecast
    daily_rows = render_daily(weather)
    if daily_rows:
        print(f"\n{theme_color}--- 3-DAY FORECAST ---{reset}")
        display_table(["Date", "Weather", "Temperature", "Precip.", "Wind"], daily_rows)

    print()
    input("Press Enter to return...")
