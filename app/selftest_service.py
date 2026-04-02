from __future__ import annotations

import shutil
import socket
import time
from dataclasses import dataclass
from typing import Any, Callable

from .audio_resolver import AudioStreamResolver
from .audio_system import AudioSystemService
from .config_manager import ControllerConfig
from .playlist_fetcher import PlaylistFetcher
from .stations import STATION_MAP
from .upnp_renderer import UpnpRendererService
from .weather_service import WeatherService


@dataclass(frozen=True, slots=True)
class SelfTestResult:
    name: str
    status: str
    detail: str
    duration_ms: int

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "duration_ms": self.duration_ms,
        }


class SelfTestService:
    def __init__(
        self,
        *,
        playlist_fetcher: PlaylistFetcher,
        audio_resolver: AudioStreamResolver,
        weather_service: WeatherService,
        audio_service: AudioSystemService,
        upnp_service: UpnpRendererService,
    ) -> None:
        self.playlist_fetcher = playlist_fetcher
        self.audio_resolver = audio_resolver
        self.weather_service = weather_service
        self.audio_service = audio_service
        self.upnp_service = upnp_service

    def run(self, selected_station_id: str, config: ControllerConfig | None = None) -> dict[str, Any]:
        station = STATION_MAP[selected_station_id]
        config = config or ControllerConfig()
        checks = [
            self._run_check("DNS / Internet", self._check_dns),
            self._run_check("Stream-URL", lambda: self._check_stream(station)),
            self._run_check("Metadaten", lambda: self._check_metadata(station)),
            self._run_check("Wetter Falkensee", self._check_weather),
            self._run_check("Audio am Raspberry Pi", self._check_audio),
            self._run_check("WLAN-Lautsprecher (UPnP)", lambda: self._check_upnp(config.audio_output_id)),
            self._run_check("Update-Backend", self._check_update_backend),
        ]
        return {
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "station": station.public_dict(),
            "checks": [check.to_public_dict() for check in checks],
            "ok": all(check.status == "ok" for check in checks if check.status != "warn"),
        }

    def _run_check(self, name: str, callback: Callable[[], str]) -> SelfTestResult:
        started = time.monotonic()
        try:
            detail = callback()
            status = "ok"
        except Warning as exc:
            detail = str(exc)
            status = "warn"
        except Exception as exc:  # noqa: BLE001
            detail = str(exc)
            status = "error"
        duration_ms = int((time.monotonic() - started) * 1000)
        return SelfTestResult(name=name, status=status, detail=detail, duration_ms=duration_ms)

    def _check_dns(self) -> str:
        socket.getaddrinfo("api.open-meteo.com", 443, type=socket.SOCK_STREAM)
        return "Namensaufloesung funktioniert"

    def _check_stream(self, station) -> str:
        stream_url = self.audio_resolver.resolve(station)
        return f"Aufgeloest: {stream_url}"

    def _check_metadata(self, station) -> str:
        now_playing = self.playlist_fetcher.fetch(station)
        return f"{now_playing.artist} - {now_playing.title}"

    def _check_weather(self) -> str:
        payload = self.weather_service.get_display_weather()
        current = payload.get("current") or {}
        if payload.get("error"):
            raise Warning(str(payload["error"]))
        return f"{payload.get('location')}: {current.get('temperature_c', '--')}°C, {current.get('condition', 'n/a')}"

    def _check_audio(self) -> str:
        state = self.audio_service.get_state()
        if not state.available:
            raise Warning(state.message or "Kein Audio-Backend aktiv")
        return f"{state.selected_output_label or 'Audio'} @ {state.volume_percent}%"

    def _check_upnp(self, selected_output_id: str) -> str:
        payload = self.upnp_service.status()
        renderers = payload.get("renderers") or []
        if not payload.get("available"):
            raise Warning(payload.get("message") or "UPnP nicht verfuegbar")
        if not renderers:
            raise Warning("Kein WLAN-Lautsprecher gefunden")
        selected_label = None
        if str(selected_output_id or "").startswith("upnp:"):
            for renderer in renderers:
                if renderer.get("id") == selected_output_id:
                    selected_label = renderer.get("friendly_name")
                    break
        if selected_label:
            return f"{selected_label} gefunden und auswählbar"
        return f"{len(renderers)} WLAN-Lautsprecher gefunden"

    def _check_update_backend(self) -> str:
        if shutil.which("git"):
            return "git verfuegbar"
        raise Warning("git nicht installiert")
