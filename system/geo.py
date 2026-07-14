"""
Модуль автоматического определения геолокации по IP-адресу.

Использует два бесплатных сервиса как fallback:
  1) ipapi.co (HTTPS, JSON, до 1000 запросов/день без ключа)
  2) ip-api.com (HTTP, JSON, до 45 запросов/мин без ключа)

Локация кэшируется в system/user_config.json (last_location) и обновляется
не чаще, чем раз в час.
"""
import json
import os
import socket
import urllib.error
import urllib.request
from typing import Optional

import config
from system.user_config import cache_location, get_cached_location

CACHE_TTL = 3600  # 1 час

# Таймаут HTTP-запросов (сек) — чтобы медленный интернет не замораживал оболочку
HTTP_TIMEOUT = 4.0

# User-Agent включает публичную версию + версию движка (Source-of-truth — config.py).
USER_AGENT = (
    f"CitadelOS/{config.VERSION} (Core {config.CORE_VERSION}; geolocation)"
)


def _http_get_json(url: str) -> Optional[dict]:
    """Безопасный GET → JSON. Возвращает dict или None при любой ошибке."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body)
    except (urllib.error.URLError, urllib.error.HTTPError, socket.timeout, json.JSONDecodeError, OSError):
        return None


def get_public_ip() -> Optional[str]:
    """Получить внешний IP-адрес. Сначала пробуем ipapi.co, потом ipify."""
    data = _http_get_json("https://api.ipify.org?format=json")
    if data and "ip" in data:
        return str(data["ip"]).strip()

    data = _http_get_json("https://api.ipapi.is/?q=")  # содержит ip
    if data and "ip" in data:
        return str(data["ip"]).strip()

    # Fallback — резолвим DNS
    try:
        return socket.gethostbyname("ifconfig.me")
    except (socket.gaierror, OSError):
        return None


def lookup_location_ipapi(ip: str) -> Optional[dict]:
    """Запрос к ipapi.co — HTTPS, наиболее стабильный."""
    data = _http_get_json(f"https://ipapi.co/{ip}/json/")
    if not data or data.get("error"):
        return None
    try:
        return {
            "ip": ip,
            "city": data.get("city") or "",
            "region": data.get("region") or "",
            "country": data.get("country_name") or data.get("country") or "",
            "country_code": data.get("country_code") or "",
            "lat": float(data.get("latitude") or 0.0),
            "lon": float(data.get("longitude") or 0.0),
            "timezone": data.get("timezone") or "",
            "org": data.get("org") or data.get("asn") or "",
            "source": "ipapi.co",
        }
    except (TypeError, ValueError):
        return None


def lookup_location_ipapi_is(ip: str) -> Optional[dict]:
    """Запрос к ipapi.is — HTTPS, fallback."""
    data = _http_get_json(f"https://api.ipapi.is/?q={ip}")
    if not data or not data.get("location"):
        return None
    loc = data.get("location") or {}
    try:
        return {
            "ip": ip,
            "city": loc.get("city") or "",
            "region": loc.get("state") or "",
            "country": loc.get("country") or "",
            "country_code": loc.get("country_code") or "",
            "lat": float(loc.get("latitude") or 0.0),
            "lon": float(loc.get("longitude") or 0.0),
            "timezone": data.get("timezone") or "",
            "org": data.get("asn") or data.get("company") or "",
            "source": "ipapi.is",
        }
    except (TypeError, ValueError):
        return None


def get_location(force_refresh: bool = False) -> Optional[dict]:
    """
    Главная функция модуля: вернуть словарь с локацией.
    Если есть свежий кэш (младше 1 часа) и force_refresh=False — вернёт его.
    Иначе — запросит IP, потом гео по IP, закэширует и вернёт.

    Возвращает None, если вообще нет интернета или сервисы недоступны.
    """
    if not force_refresh:
        cached = get_cached_location(max_age_seconds=CACHE_TTL)
        if cached:
            return cached

    ip = get_public_ip()
    if not ip:
        return None

    loc = lookup_location_ipapi(ip) or lookup_location_ipapi_is(ip)
    if not loc:
        return None

    cache_location(loc)
    return loc


def format_location(loc: dict) -> str:
    """Отформатировать локацию для красивого вывода в терминале."""
    if not loc:
        return "Локация не определена"

    city = loc.get("city") or "—"
    region = loc.get("region") or ""
    country = loc.get("country") or "—"
    ip = loc.get("ip") or "—"
    tz = loc.get("timezone") or "—"
    org = loc.get("org") or "—"
    src = loc.get("source") or "—"

    parts = [f"{city}"]
    if region and region != city:
        parts.append(region)
    parts.append(country)
    place = ", ".join(parts)

    return (
        f"IP: {ip}\n"
        f"Место: {place}\n"
        f"Часовой пояс: {tz}\n"
        f"Провайдер: {org}\n"
        f"Координаты: {loc.get('lat'):.4f}, {loc.get('lon'):.4f}\n"
        f"Источник: {src}"
    )
