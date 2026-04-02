from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any


VOLUME_RE = re.compile(r"(\d+)%")


@dataclass(frozen=True, slots=True)
class AudioOutput:
    id: str
    label: str
    kind: str
    default: bool
    raw_name: str
    backend_ref: str

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "default": self.default,
            "raw_name": self.raw_name,
            "backend_ref": self.backend_ref,
        }


@dataclass(frozen=True, slots=True)
class AudioState:
    available: bool
    backend: str
    volume_percent: int
    muted: bool
    outputs: tuple[AudioOutput, ...]
    selected_output_id: str | None
    selected_output_label: str | None
    message: str | None = None
    route_kind: str = "local"
    supports_transport: bool = False
    transport_playing: bool = False

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "backend": self.backend,
            "volume_percent": self.volume_percent,
            "muted": self.muted,
            "outputs": [output.to_public_dict() for output in self.outputs],
            "selected_output_id": self.selected_output_id,
            "selected_output_label": self.selected_output_label,
            "message": self.message,
            "route_kind": self.route_kind,
            "supports_transport": self.supports_transport,
            "transport_playing": self.transport_playing,
        }


class AudioSystemService:
    def __init__(self) -> None:
        self.wpctl_path = shutil.which("wpctl")
        self.pactl_path = shutil.which("pactl")

    def get_state(self) -> AudioState:
        if self.pactl_path:
            try:
                return self._state_from_pactl()
            except Exception as exc:  # noqa: BLE001
                pactl_error = str(exc)
            else:
                pactl_error = None
        else:
            pactl_error = "pactl nicht installiert"

        if self.wpctl_path:
            try:
                return self._state_from_wpctl()
            except Exception as exc:  # noqa: BLE001
                return AudioState(
                    available=False,
                    backend="wpctl",
                    volume_percent=0,
                    muted=False,
                    outputs=(),
                    selected_output_id=None,
                    selected_output_label=None,
                    message=f"Audio-Backend nicht verfuegbar: {exc}",
                )

        return AudioState(
            available=False,
            backend="none",
            volume_percent=0,
            muted=False,
            outputs=(),
            selected_output_id=None,
            selected_output_label=None,
            message=pactl_error or "Kein Audio-Backend gefunden",
        )

    def set_volume(self, percent: int) -> AudioState:
        percent = max(0, min(100, int(percent)))
        if self.pactl_path:
            self._run([self.pactl_path, "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"])
            return self.get_state()
        if self.wpctl_path:
            self._run([self.wpctl_path, "set-volume", "@DEFAULT_SINK@", f"{percent}%"])
            return self.get_state()
        raise RuntimeError("Kein Audio-Backend gefunden")

    def change_volume(self, delta_percent: int) -> AudioState:
        current = self.get_state()
        return self.set_volume(current.volume_percent + int(delta_percent))

    def set_muted(self, muted: bool) -> AudioState:
        value = "1" if muted else "0"
        if self.pactl_path:
            self._run([self.pactl_path, "set-sink-mute", "@DEFAULT_SINK@", value])
            return self.get_state()
        if self.wpctl_path:
            self._run([self.wpctl_path, "set-mute", "@DEFAULT_SINK@", value])
            return self.get_state()
        raise RuntimeError("Kein Audio-Backend gefunden")

    def toggle_mute(self) -> AudioState:
        state = self.get_state()
        return self.set_muted(not state.muted)

    def set_output(self, output_id: str) -> AudioState:
        state = self.get_state()
        output = self._resolve_output_selection(state.outputs, output_id)
        if output is None:
            raise ValueError(f"Unbekannte Audioausgabe: {output_id}")

        if state.backend == "pactl" and self.pactl_path:
            self._run([self.pactl_path, "set-default-sink", output.backend_ref])
            return self.get_state()
        if state.backend == "wpctl" and self.wpctl_path:
            self._run([self.wpctl_path, "set-default", output.backend_ref])
            return self.get_state()
        raise RuntimeError("Audioausgabe kann mit dem aktuellen Backend nicht umgeschaltet werden")

    def _resolve_output_selection(self, outputs: tuple[AudioOutput, ...], output_id: str) -> AudioOutput | None:
        if output_id in {"jack", "klinke"}:
            for output in outputs:
                if output.kind == "jack":
                    return output
            return None
        for output in outputs:
            if output.id == output_id or output.backend_ref == output_id:
                return output
        return None

    def _state_from_pactl(self) -> AudioState:
        info = self._run([self.pactl_path, "info"])
        default_sink = _parse_pactl_default_sink(info)
        blocks = _parse_pactl_sinks(self._run([self.pactl_path, "list", "sinks"]))
        if not blocks:
            raise RuntimeError("Keine Audioausgabe gefunden")

        outputs: list[AudioOutput] = []
        selected_label = None
        volume_percent = 0
        muted = False
        selected_output_id = None

        for block in blocks:
            name = block.get("name") or block.get("description") or block.get("index") or "unbekannt"
            kind = _classify_output(name, block.get("description") or "")
            output_id = _output_id(name, kind)
            is_default = default_sink == name
            output = AudioOutput(
                id=output_id,
                label=_display_label(block.get("description") or name, kind),
                kind=kind,
                default=is_default,
                raw_name=name,
                backend_ref=name,
            )
            outputs.append(output)
            if is_default:
                selected_label = output.label
                selected_output_id = output.id
                volume_percent = int(block.get("volume_percent") or 0)
                muted = bool(block.get("muted"))

        if selected_output_id is None and outputs:
            outputs[0] = AudioOutput(
                id=outputs[0].id,
                label=outputs[0].label,
                kind=outputs[0].kind,
                default=True,
                raw_name=outputs[0].raw_name,
                backend_ref=outputs[0].backend_ref,
            )
            selected_output_id = outputs[0].id
            selected_label = outputs[0].label
            block = blocks[0]
            volume_percent = int(block.get("volume_percent") or 0)
            muted = bool(block.get("muted"))

        return AudioState(
            available=True,
            backend="pactl",
            volume_percent=volume_percent,
            muted=muted,
            outputs=tuple(outputs),
            selected_output_id=selected_output_id,
            selected_output_label=selected_label,
            message=None,
        )

    def _state_from_wpctl(self) -> AudioState:
        status = self._run([self.wpctl_path, "status", "-n"])
        sink_entries = _parse_wpctl_sinks(status)
        if not sink_entries:
            raise RuntimeError("Keine Audioausgabe gefunden")
        volume_output = self._run([self.wpctl_path, "get-volume", "@DEFAULT_SINK@"])
        volume_percent, muted = _parse_wpctl_volume(volume_output)

        outputs: list[AudioOutput] = []
        selected_output_id = None
        selected_label = None
        for entry in sink_entries:
            kind = _classify_output(entry["name"], entry["name"])
            output_id = _output_id(entry["name"], kind)
            output = AudioOutput(
                id=output_id,
                label=_display_label(entry["name"], kind),
                kind=kind,
                default=entry["default"],
                raw_name=entry["name"],
                backend_ref=entry["id"],
            )
            outputs.append(output)
            if entry["default"]:
                selected_output_id = output.id
                selected_label = output.label

        if selected_output_id is None and outputs:
            selected_output_id = outputs[0].id
            selected_label = outputs[0].label

        return AudioState(
            available=True,
            backend="wpctl",
            volume_percent=volume_percent,
            muted=muted,
            outputs=tuple(outputs),
            selected_output_id=selected_output_id,
            selected_output_label=selected_label,
            message=None,
        )

    @staticmethod
    def _run(cmd: list[str]) -> str:
        completed = subprocess.run(
            cmd,
            check=True,
            text=True,
            capture_output=True,
            timeout=15,
        )
        return completed.stdout


def _parse_pactl_default_sink(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("Default Sink:"):
            value = line.partition(":")[2].strip()
            return value or None
    return None


def _parse_pactl_sinks(text: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith("Sink #"):
            if current:
                blocks.append(current)
            current = {"index": stripped.partition("#")[2].strip(), "muted": False, "volume_percent": 0}
            continue
        if current is None:
            continue
        if stripped.startswith("Name:"):
            current["name"] = stripped.partition(":")[2].strip()
        elif stripped.startswith("Description:"):
            current["description"] = stripped.partition(":")[2].strip()
        elif stripped.startswith("Mute:"):
            current["muted"] = stripped.partition(":")[2].strip().casefold() == "yes"
        elif stripped.startswith("Volume:") and not current.get("volume_percent"):
            match = VOLUME_RE.search(stripped)
            if match:
                current["volume_percent"] = int(match.group(1))
    if current:
        blocks.append(current)
    return blocks


def _parse_wpctl_sinks(text: str) -> list[dict[str, Any]]:
    lines = text.splitlines()
    in_sinks = False
    sinks: list[dict[str, Any]] = []
    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        cleaned = stripped.lstrip("│├└─ ").strip()
        if cleaned.startswith("Sinks:"):
            in_sinks = True
            continue
        if not in_sinks:
            continue
        if cleaned.endswith(":") and not re.match(r"^\*?\s*\d+\.", cleaned):
            break
        match = re.match(r"^(\*)?\s*(\d+)\.\s+(.+)$", cleaned)
        if not match:
            continue
        sinks.append(
            {
                "default": bool(match.group(1)),
                "id": match.group(2),
                "name": re.sub(r"\s*\[vol:.*\]$", "", match.group(3).strip()),
            }
        )
    return sinks


def _parse_wpctl_volume(text: str) -> tuple[int, bool]:
    percent = 0
    muted = "MUTED" in text.upper()
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)", text)
    if match:
        try:
            percent = int(round(float(match.group(1)) * 100))
        except ValueError:
            percent = 0
    return max(0, min(150, percent)), muted


def _classify_output(name: str, description: str) -> str:
    haystack = f"{name} {description}".casefold()
    if "bluez" in haystack or "bluetooth" in haystack:
        return "bluetooth"
    if "analog" in haystack or "headphone" in haystack or "headphones" in haystack or "bcm2835" in haystack or "klinke" in haystack:
        return "jack"
    return "other"


def _display_label(raw: str, kind: str) -> str:
    cleaned = raw.strip() or "Audioausgabe"
    if kind == "jack":
        return "Klinke"
    if kind == "bluetooth":
        return cleaned
    return cleaned


def _output_id(raw_name: str, kind: str) -> str:
    if kind == "jack":
        return "jack"
    value = raw_name.strip().casefold()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or kind
