from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from .config_manager import ControllerConfig
from .settings import settings


@dataclass(frozen=True, slots=True)
class DisplayScheduleState:
    enabled: bool
    on_hour: int
    off_hour: int
    awake: bool
    timezone: str
    message: str

    def to_public_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "on_hour": self.on_hour,
            "off_hour": self.off_hour,
            "awake": self.awake,
            "timezone": self.timezone,
            "message": self.message,
        }


class DisplayScheduleService:
    def __init__(self) -> None:
        self.zone = ZoneInfo(settings.weather_timezone)

    def current_state(self, config: ControllerConfig) -> DisplayScheduleState:
        enabled = bool(config.display_schedule_enabled)
        on_hour = int(config.display_on_hour)
        off_hour = int(config.display_off_hour)
        now = datetime.now(self.zone)
        current_hour = now.hour
        if not enabled:
            awake = True
            message = "Anzeige-Zeitfenster deaktiviert"
        else:
            awake = _is_hour_in_active_range(current_hour, on_hour, off_hour)
            message = f"Aktiv von {on_hour:02d}:00 bis {off_hour:02d}:00"
        return DisplayScheduleState(
            enabled=enabled,
            on_hour=on_hour,
            off_hour=off_hour,
            awake=awake,
            timezone=settings.weather_timezone,
            message=message,
        )


def _is_hour_in_active_range(current_hour: int, on_hour: int, off_hour: int) -> bool:
    if on_hour == off_hour:
        return True
    if on_hour < off_hour:
        return on_hour <= current_hour < off_hour
    return current_hour >= on_hour or current_hour < off_hour
