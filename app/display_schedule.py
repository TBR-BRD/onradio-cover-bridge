from __future__ import annotations

from dataclasses import dataclass

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
    def current_state(self, config: ControllerConfig) -> DisplayScheduleState:
        enabled = False
        on_hour = int(config.display_on_hour)
        off_hour = int(config.display_off_hour)
        awake = True
        message = "Anzeige bleibt dauerhaft aktiv"
        return DisplayScheduleState(
            enabled=enabled,
            on_hour=on_hour,
            off_hour=off_hour,
            awake=awake,
            timezone=settings.weather_timezone,
            message=message,
        )
