from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .settings import settings


@dataclass(slots=True)
class ControllerConfig:
    display_schedule_enabled: bool = True
    display_on_hour: int = 8
    display_off_hour: int = 22
    transitions_enabled: bool = True
    update_source_zip_url: str = ""
    audio_output_id: str = "jack"

    def normalize(self) -> None:
        self.display_on_hour = max(0, min(23, int(self.display_on_hour)))
        self.display_off_hour = max(0, min(23, int(self.display_off_hour)))
        self.display_schedule_enabled = bool(self.display_schedule_enabled)
        self.transitions_enabled = bool(self.transitions_enabled)
        self.update_source_zip_url = str(self.update_source_zip_url or "").strip()
        self.audio_output_id = str(self.audio_output_id or "jack").strip() or "jack"

    def update_from_payload(self, payload: dict[str, Any]) -> None:
        if "display_schedule_enabled" in payload:
            self.display_schedule_enabled = bool(payload["display_schedule_enabled"])
        if "display_on_hour" in payload:
            self.display_on_hour = int(payload["display_on_hour"])
        if "display_off_hour" in payload:
            self.display_off_hour = int(payload["display_off_hour"])
        if "transitions_enabled" in payload:
            self.transitions_enabled = bool(payload["transitions_enabled"])
        if "update_source_zip_url" in payload:
            self.update_source_zip_url = str(payload["update_source_zip_url"] or "").strip()
        if "audio_output_id" in payload:
            self.audio_output_id = str(payload["audio_output_id"] or "jack").strip() or "jack"
        self.normalize()

    def to_public_dict(self) -> dict[str, Any]:
        return asdict(self)


class ConfigRepository:
    def __init__(self, config_file: Path | None = None, backup_dir: Path | None = None) -> None:
        self.config_file = config_file or settings.config_file
        self.backup_dir = backup_dir or settings.config_backup_dir
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> ControllerConfig:
        config = ControllerConfig()
        if not self.config_file.exists():
            return config
        try:
            payload = json.loads(self.config_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return config
        try:
            config.update_from_payload(payload)
        except Exception:
            return ControllerConfig()
        return config

    def save(self, config: ControllerConfig, *, create_backup: bool = True) -> None:
        config.normalize()
        payload = config.to_public_dict()
        serialized = json.dumps(payload, ensure_ascii=False, indent=2)
        self.config_file.write_text(serialized, encoding="utf-8")
        if create_backup:
            self._write_backup(payload)
            self._prune_backups(settings.config_backup_keep)

    def manual_backup(self, config: ControllerConfig) -> Path:
        config.normalize()
        payload = config.to_public_dict()
        return self._write_backup(payload)

    def list_backups(self) -> list[dict[str, Any]]:
        backups: list[dict[str, Any]] = []
        for path in sorted(self.backup_dir.glob("config-*.json"), reverse=True):
            try:
                stat = path.stat()
            except OSError:
                continue
            backups.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "size": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                }
            )
        return backups

    def _write_backup(self, payload: dict[str, Any]) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = self.backup_dir / f"config-{timestamp}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def _prune_backups(self, keep: int) -> None:
        if keep <= 0:
            return
        backups = sorted(self.backup_dir.glob("config-*.json"), reverse=True)
        for obsolete in backups[keep:]:
            try:
                obsolete.unlink()
            except OSError:
                continue
