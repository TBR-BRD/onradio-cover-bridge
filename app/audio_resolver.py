from __future__ import annotations

import re
import threading
import time

import requests

from .settings import settings
from .stations import Station

PLS_FILE_RE = re.compile(r"^File\d+=(.+)$", re.IGNORECASE)


class AudioStreamResolver:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": settings.user_agent})
        self._cache: dict[str, tuple[float, str]] = {}
        self._lock = threading.Lock()

    def resolve(self, station: Station) -> str:
        if station.audio_mode == "direct":
            return station.audio_url
        if station.audio_mode == "pls":
            return self._resolve_pls(station)
        if station.audio_mode == "m3u":
            return self._resolve_m3u(station)
        raise ValueError(f"Unbekannter Audio-Modus: {station.audio_mode}")

    def _resolve_pls(self, station: Station) -> str:
        with self._lock:
            cached = self._cache.get(station.id)
            if cached and cached[0] > time.monotonic():
                return cached[1]

        response = self.session.get(
            station.audio_url,
            timeout=(5, settings.playlist_timeout_seconds),
        )
        response.raise_for_status()

        resolved_url = _parse_pls(response.text)
        with self._lock:
            self._cache[station.id] = (time.monotonic() + 60.0, resolved_url)
        return resolved_url

    def _resolve_m3u(self, station: Station) -> str:
        with self._lock:
            cached = self._cache.get(station.id)
            if cached and cached[0] > time.monotonic():
                return cached[1]

        response = self.session.get(
            station.audio_url,
            timeout=(5, settings.playlist_timeout_seconds),
        )
        response.raise_for_status()

        resolved_url = _parse_m3u(response.text)
        with self._lock:
            self._cache[station.id] = (time.monotonic() + 60.0, resolved_url)
        return resolved_url


def _parse_pls(text: str) -> str:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        match = PLS_FILE_RE.match(line)
        if not match:
            continue
        url = match.group(1).strip()
        if url:
            return url
    raise ValueError("In der PLS-Datei wurde keine Stream-URL gefunden.")


def _parse_m3u(text: str) -> str:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('http://') or line.startswith('https://'):
            return line
    raise ValueError("In der M3U-Datei wurde keine Stream-URL gefunden.")
