from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from .settings import settings

logger = logging.getLogger("onradio_cover_bridge")

ALLOWED_AUDIO_MODES = {"direct", "pls", "m3u"}
CUSTOM_STATION_ID_PREFIX = "custom-"
_FALLBACK_STATIONS_PATH = Path(__file__).resolve().parent / "stations_fallback.json"


@dataclass(frozen=True, slots=True)
class Station:
    id: str
    name: str
    homepage_url: str
    audio_url: str
    metadata_url: str
    audio_mode: str = "direct"
    metadata_mode: str = "on_playlist_html"
    metadata_fallback_url: str | None = None
    metadata_fallback_mode: str | None = None
    metadata_station_label: str | None = None
    metadata_station_aliases: tuple[str, ...] = ()
    metadata_station_id: int | None = None
    is_custom: bool = False

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "stream_url": f"/stream/{self.id}",
            "homepage_url": self.homepage_url,
            "audio_url": self.audio_url,
            "audio_mode": self.audio_mode,
            "custom": self.is_custom,
            "removable": True,
        }


def _station_from_dict(d: dict[str, Any]) -> Station:
    return Station(
        id=d["id"],
        name=d["name"],
        homepage_url=d.get("homepageUrl", ""),
        audio_url=d["audioUrl"],
        metadata_url=d["metadataUrl"],
        audio_mode=d.get("audioMode", "direct"),
        metadata_mode=d.get("metadataMode", "icy_stream"),
        metadata_fallback_url=d.get("metadataFallbackUrl"),
        metadata_fallback_mode=d.get("metadataFallbackMode"),
        metadata_station_label=d.get("metadataStationLabel"),
        metadata_station_aliases=tuple(d.get("metadataStationAliases") or ()),
        metadata_station_id=d.get("metadataStationId"),
    )


def _load_builtin_stations() -> tuple[Station, ...]:
    """Loads the built-in station catalog.

    The canonical, hand-authored source of this catalog lives in the
    separate `radiostations` repo (https://github.com/TBR-BRD/radiostations),
    not in this project - this function fetches the current
    `stations.json` it publishes. A local cache file is written on every
    successful fetch and used as a fallback if a later fetch fails (no
    network, GitHub unreachable, ...); a snapshot bundled with this
    repository (`stations_fallback.json`) is the last resort for a brand
    new install that has never had a successful fetch yet.

    This runs once at import time (matching the previous behaviour, where
    the catalog was a hardcoded constant fixed for the process lifetime) -
    picking up a change in `radiostations` requires a restart.
    """
    data: list[dict[str, Any]] | None = None

    try:
        response = requests.get(settings.stations_catalog_url, timeout=settings.stations_fetch_timeout_seconds)
        response.raise_for_status()
        fetched = response.json()
        if isinstance(fetched, list) and fetched:
            data = fetched
            try:
                settings.stations_cache_file.parent.mkdir(parents=True, exist_ok=True)
                settings.stations_cache_file.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            except OSError as exc:
                logger.warning("Could not write station catalog cache: %s", exc)
        else:
            logger.warning("Station catalog at %s was empty or malformed", settings.stations_catalog_url)
    except Exception as exc:  # noqa: BLE001 - any failure here must not crash startup
        logger.warning("Could not fetch station catalog from %s: %s", settings.stations_catalog_url, exc)

    if data is None and settings.stations_cache_file.exists():
        try:
            data = json.loads(settings.stations_cache_file.read_text(encoding="utf-8"))
            logger.info("Using cached station catalog from %s", settings.stations_cache_file)
        except (OSError, ValueError) as exc:
            logger.warning("Could not read station catalog cache: %s", exc)

    if data is None:
        data = json.loads(_FALLBACK_STATIONS_PATH.read_text(encoding="utf-8"))
        logger.warning(
            "Using bundled fallback station catalog (%s) - network fetch and cache both unavailable",
            _FALLBACK_STATIONS_PATH,
        )

    return tuple(_station_from_dict(entry) for entry in data)


STATIONS: tuple[Station, ...] = _load_builtin_stations()

STATION_MAP: dict[str, Station] = {station.id: station for station in STATIONS}
DEFAULT_STATION_ID = STATIONS[0].id


def station_catalog(config: Any | None = None) -> tuple[Station, ...]:
    hidden_station_ids = _normalized_hidden_station_ids(getattr(config, "hidden_station_ids", ()))
    catalog = [station for station in STATIONS if station.id not in hidden_station_ids]
    existing_ids = {station.id for station in STATIONS}
    for payload in getattr(config, "custom_stations", ()) or ():
        station = station_from_payload(payload, existing_ids=existing_ids)
        if station is None:
            continue
        catalog.append(station)
        existing_ids.add(station.id)
    return tuple(catalog) or (STATIONS[0],)


def station_map(config: Any | None = None) -> dict[str, Station]:
    return {station.id: station for station in station_catalog(config)}


def first_station_id(config: Any | None = None) -> str:
    return station_catalog(config)[0].id


def normalize_custom_station_payload(payload: dict[str, Any], existing_ids: set[str] | None = None) -> dict[str, Any]:
    existing_ids = set(existing_ids or set())
    name = _clean_text(payload.get("name"), max_length=80)
    audio_url = _clean_url(payload.get("audio_url"))
    homepage_url = _clean_url(payload.get("homepage_url"), allow_empty=True)
    audio_mode = _clean_audio_mode(payload.get("audio_mode"))
    if not name:
        raise ValueError("Sendername fehlt")
    if not audio_url:
        raise ValueError("Stream-URL fehlt oder ist ungueltig")

    station_id = _clean_station_id(payload.get("id"))
    if not station_id or station_id in STATION_MAP or station_id in existing_ids:
        station_id = _unique_station_id(name, existing_ids | set(STATION_MAP))

    return {
        "id": station_id,
        "name": name,
        "homepage_url": homepage_url,
        "audio_url": audio_url,
        "audio_mode": audio_mode,
    }


def station_from_payload(payload: Any, existing_ids: set[str] | None = None) -> Station | None:
    if not isinstance(payload, dict):
        return None
    try:
        normalized = normalize_custom_station_payload(payload, existing_ids=existing_ids)
    except ValueError:
        return None
    return Station(
        id=normalized["id"],
        name=normalized["name"],
        homepage_url=normalized["homepage_url"],
        audio_url=normalized["audio_url"],
        metadata_url=normalized["audio_url"],
        audio_mode=normalized["audio_mode"],
        metadata_mode="icy_stream",
        is_custom=True,
    )


def _normalized_hidden_station_ids(values: Any) -> set[str]:
    if not isinstance(values, (list, tuple, set)):
        return set()
    return {str(value).strip() for value in values if str(value).strip() in STATION_MAP}


def _clean_text(value: Any, *, max_length: int) -> str:
    return " ".join(str(value or "").split())[:max_length]


def _clean_url(value: Any, *, allow_empty: bool = False) -> str:
    url = str(value or "").strip()
    if not url and allow_empty:
        return ""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return url


def _clean_audio_mode(value: Any) -> str:
    mode = str(value or "direct").strip().casefold()
    return mode if mode in ALLOWED_AUDIO_MODES else "direct"


def _clean_station_id(value: Any) -> str:
    station_id = str(value or "").strip().casefold()
    if not station_id.startswith(CUSTOM_STATION_ID_PREFIX):
        return ""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,78}[a-z0-9]", station_id):
        return ""
    return station_id


def _unique_station_id(name: str, existing_ids: set[str]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
    slug = slug or "radio"
    candidate = f"{CUSTOM_STATION_ID_PREFIX}{slug}"[:80].strip("-")
    if candidate not in existing_ids:
        return candidate
    suffix = 2
    while True:
        trimmed = candidate[: max(1, 80 - len(str(suffix)) - 1)].strip("-")
        next_candidate = f"{trimmed}-{suffix}"
        if next_candidate not in existing_ids:
            return next_candidate
        suffix += 1
