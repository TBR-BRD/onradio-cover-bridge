from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .settings import settings
from .stations import DEFAULT_STATION_ID, STATION_MAP, Station


UTC = timezone.utc


@dataclass(slots=True)
class SharedState:
    selected_station_id: str = DEFAULT_STATION_ID
    playing_hint: bool = False
    played_at: str | None = None
    artist: str | None = None
    title: str | None = None
    cover_url: str | None = None
    cover_source: str | None = None
    status_text: str = "Bereit"
    error: str | None = None
    updated_at: str = field(default_factory=lambda: _now_iso())

    def to_public_dict(self) -> dict[str, Any]:
        station = self.station
        return {
            **asdict(self),
            "station": station.public_dict(),
        }

    @property
    def station(self) -> Station:
        return STATION_MAP[self.selected_station_id]

    @property
    def track_key(self) -> tuple[str | None, str | None, str]:
        return self.artist, self.title, self.selected_station_id

    def set_selected_station(self, station_id: str) -> None:
        if station_id not in STATION_MAP:
            raise KeyError(station_id)
        self.selected_station_id = station_id
        self.status_text = "Sender gewechselt"
        self.error = None
        self.updated_at = _now_iso()

    def set_playing_hint(self, playing: bool) -> None:
        self.playing_hint = playing
        self.status_text = "Wiedergabe läuft" if playing else "Pausiert"
        self.updated_at = _now_iso()

    def set_track(
        self,
        *,
        played_at: str | None,
        artist: str,
        title: str,
        cover_url: str | None,
        cover_source: str | None,
    ) -> None:
        self.played_at = played_at
        self.artist = artist
        self.title = title
        self.cover_url = cover_url
        self.cover_source = cover_source
        self.error = None
        self.status_text = "Wiedergabe läuft" if self.playing_hint else "Metadaten aktualisiert"
        self.updated_at = _now_iso()

    def set_error(self, message: str) -> None:
        self.error = message
        self.status_text = "Fehler beim Aktualisieren"
        self.updated_at = _now_iso()


class StateRepository:
    def __init__(self, state_file: Path | None = None) -> None:
        self.state_file = state_file or settings.state_file
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> SharedState:
        if not self.state_file.exists():
            return SharedState()

        try:
            payload = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return SharedState()

        state = SharedState()
        state.selected_station_id = payload.get("selected_station_id", DEFAULT_STATION_ID)
        if state.selected_station_id not in STATION_MAP:
            state.selected_station_id = DEFAULT_STATION_ID
        state.playing_hint = bool(payload.get("playing_hint", False))
        state.played_at = payload.get("played_at")
        state.artist = payload.get("artist")
        state.title = payload.get("title")
        state.cover_url = payload.get("cover_url")
        state.cover_source = payload.get("cover_source")
        state.status_text = payload.get("status_text", "Bereit")
        state.error = payload.get("error")
        state.updated_at = payload.get("updated_at") or _now_iso()
        return state

    def save(self, state: SharedState) -> None:
        payload = asdict(state)
        self.state_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )



def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")
