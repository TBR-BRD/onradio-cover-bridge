from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

import requests

from .settings import settings

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
DEFAULT_ICON_SLUG = "partly-cloudy"

WEATHER_CODE_MAP: dict[int, tuple[str, str]] = {
    0: ("Sonnig", "sunny"),
    1: ("Meist klar", "mostly-clear"),
    2: ("Teilweise bewölkt", "partly-cloudy"),
    3: ("Bewölkt", "cloudy"),
    45: ("Nebel", "fog"),
    48: ("Raureifnebel", "fog"),
    51: ("Leichter Nieselregen", "drizzle"),
    53: ("Nieselregen", "drizzle"),
    55: ("Starker Nieselregen", "rain"),
    56: ("Leichter gefrierender Nieselregen", "freezing"),
    57: ("Gefrierender Nieselregen", "freezing"),
    61: ("Leichter Regen", "drizzle"),
    63: ("Regen", "rain"),
    65: ("Starker Regen", "rain"),
    66: ("Leichter gefrierender Regen", "freezing"),
    67: ("Gefrierender Regen", "freezing"),
    71: ("Leichter Schneefall", "snow"),
    73: ("Schneefall", "snow"),
    75: ("Starker Schneefall", "snow"),
    77: ("Schneegriesel", "snow"),
    80: ("Leichte Schauer", "drizzle"),
    81: ("Schauer", "rain"),
    82: ("Starke Schauer", "rain"),
    85: ("Leichte Schneeschauer", "snow"),
    86: ("Schneeschauer", "snow"),
    95: ("Gewitter", "thunder"),
    96: ("Gewitter mit Hagel", "thunder"),
    99: ("Starkes Gewitter", "thunder"),
}

PRESSURE_TREND_DELTA_HPA = 1


@dataclass(frozen=True, slots=True)
class LocationResult:
    name: str
    latitude: float
    longitude: float


class WeatherService:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": settings.user_agent})
        self._lock = threading.Lock()
        self._location_cache: tuple[float, LocationResult] | None = None
        self._forecast_cache: tuple[float, dict[str, Any]] | None = None

    def get_display_weather(self) -> dict[str, Any]:
        if not settings.weather_enabled:
            return {
                "location": settings.weather_location_name,
                "days": [],
                "error": "Wetter deaktiviert",
            }

        now = time.monotonic()
        with self._lock:
            cached = self._forecast_cache
            if cached and cached[0] > now:
                return cached[1]
            previous_pressure_hpa = _extract_pressure(cached[1]) if cached else None

        try:
            location = self._resolve_location()
            payload = self._fetch_forecast(location, previous_pressure_hpa=previous_pressure_hpa)
        except Exception as exc:  # noqa: BLE001 - kiosk mode should prefer stale cache
            with self._lock:
                cached = self._forecast_cache
                if cached:
                    stale_payload = dict(cached[1])
                    stale_payload["error"] = f"Wetter nicht aktualisiert: {exc}"
                    return stale_payload
            raise

        with self._lock:
            self._forecast_cache = (time.monotonic() + settings.weather_cache_seconds, payload)
        return payload

    def _resolve_location(self) -> LocationResult:
        now = time.monotonic()
        with self._lock:
            cached = self._location_cache
            if cached and cached[0] > now:
                return cached[1]

        response = self.session.get(
            GEOCODING_URL,
            params={
                "name": settings.weather_location_name,
                "count": 1,
                "format": "json",
                "language": "de",
                "countryCode": settings.weather_country_code,
            },
            timeout=(5, settings.weather_timeout_seconds),
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results") or []
        if not results:
            raise RuntimeError(f"Ort nicht gefunden: {settings.weather_location_name}")

        first = results[0]
        location = LocationResult(
            name=str(first.get("name") or settings.weather_location_name),
            latitude=float(first["latitude"]),
            longitude=float(first["longitude"]),
        )
        with self._lock:
            self._location_cache = (time.monotonic() + 86400.0, location)
        return location

    def _fetch_forecast(
        self,
        location: LocationResult,
        *,
        previous_pressure_hpa: int | None = None,
    ) -> dict[str, Any]:
        response = self.session.get(
            FORECAST_URL,
            params={
                "latitude": location.latitude,
                "longitude": location.longitude,
                "timezone": settings.weather_timezone,
                "forecast_days": 2,
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "current": "temperature_2m,surface_pressure,weather_code",
                "temperature_unit": "celsius",
            },
            timeout=(5, settings.weather_timeout_seconds),
        )
        response.raise_for_status()
        payload = response.json()
        daily = payload.get("daily") or {}
        current = payload.get("current") or {}

        times = daily.get("time") or []
        weather_codes = daily.get("weather_code") or []
        temp_max = daily.get("temperature_2m_max") or []
        temp_min = daily.get("temperature_2m_min") or []
        precip_max = daily.get("precipitation_probability_max") or []

        day_labels = ["Heute", "Morgen"]
        days: list[dict[str, Any]] = []
        count = min(2, len(times), len(weather_codes), len(temp_max), len(temp_min))
        for index in range(count):
            code = int(weather_codes[index])
            condition, icon_slug = WEATHER_CODE_MAP.get(code, ("Wetter", DEFAULT_ICON_SLUG))
            days.append(
                {
                    "label": day_labels[index] if index < len(day_labels) else times[index],
                    "date": times[index],
                    "condition": condition,
                    "icon_slug": icon_slug,
                    "icon_url": _icon_url(icon_slug),
                    "temp_max_c": _round_temperature(temp_max[index]),
                    "temp_min_c": _round_temperature(temp_min[index]),
                    "precipitation_probability_max": _round_percentage(
                        precip_max[index] if index < len(precip_max) else None,
                    ),
                }
            )

        current_payload = self._build_current_payload(current, previous_pressure_hpa=previous_pressure_hpa)

        return {
            "location": location.name,
            "current": current_payload,
            "days": days,
            "error": None,
        }

    def _build_current_payload(
        self,
        current: dict[str, Any],
        *,
        previous_pressure_hpa: int | None = None,
    ) -> dict[str, Any]:
        code = _safe_int(current.get("weather_code"))
        condition, icon_slug = WEATHER_CODE_MAP.get(code, ("Aktuelles Wetter", DEFAULT_ICON_SLUG)) if code is not None else ("Aktuelles Wetter", DEFAULT_ICON_SLUG)
        current_pressure_hpa = _round_pressure(current.get("surface_pressure"))
        pressure_trend = _pressure_trend(previous_pressure_hpa, current_pressure_hpa)
        return {
            "temperature_c": _round_temperature(current.get("temperature_2m")),
            "surface_pressure_hpa": current_pressure_hpa,
            "surface_pressure_trend": pressure_trend,
            "condition": condition,
            "icon_slug": icon_slug,
            "icon_url": _icon_url(icon_slug),
        }


def _icon_url(icon_slug: str) -> str:
    safe_slug = icon_slug.strip() or DEFAULT_ICON_SLUG
    return f"/static/weather-icons/{safe_slug}.svg"


def _round_temperature(value: Any) -> int | None:
    if value is None:
        return None
    return int(round(float(value)))



def _round_percentage(value: Any) -> int | None:
    if value is None:
        return None
    return int(round(float(value)))



def _round_pressure(value: Any) -> int | None:
    if value is None:
        return None
    return int(round(float(value)))



def _extract_pressure(payload: dict[str, Any] | None) -> int | None:
    if not payload:
        return None
    current = payload.get("current") or {}
    return _round_pressure(current.get("surface_pressure_hpa"))



def _pressure_trend(previous_pressure_hpa: int | None, current_pressure_hpa: int | None) -> str | None:
    if previous_pressure_hpa is None or current_pressure_hpa is None:
        return None
    delta = current_pressure_hpa - previous_pressure_hpa
    if delta >= PRESSURE_TREND_DELTA_HPA:
        return "up"
    if delta <= -PRESSURE_TREND_DELTA_HPA:
        return "down"
    return "steady"



def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
