from __future__ import annotations

import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any


MAC_RE = re.compile(r"([0-9A-F]{2}(?::[0-9A-F]{2}){5})", re.IGNORECASE)
DEVICE_RE = re.compile(r"^Device\s+([0-9A-F:]{17})\s+(.+)$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class BluetoothDevice:
    address: str
    name: str
    alias: str | None
    paired: bool
    trusted: bool
    connected: bool
    blocked: bool

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "name": self.name,
            "alias": self.alias,
            "paired": self.paired,
            "trusted": self.trusted,
            "connected": self.connected,
            "blocked": self.blocked,
        }


class BluetoothService:
    def __init__(self) -> None:
        self.binary = shutil.which("bluetoothctl")
        self._scan_lock = threading.Lock()
        self._scan_active = False
        self._last_scan_finished_at: float | None = None

    def status(self) -> dict[str, Any]:
        available = self.binary is not None
        powered = False
        message = None
        if available:
            try:
                powered = self._adapter_powered()
            except Exception as exc:  # noqa: BLE001
                message = str(exc)
        else:
            message = "bluetoothctl nicht installiert"
        return {
            "available": available,
            "powered": powered,
            "scan_active": self._scan_active,
            "last_scan_finished_at": self._last_scan_finished_at,
            "message": message,
        }

    def list_devices(self) -> list[BluetoothDevice]:
        if not self.binary:
            return []
        devices = _parse_device_list(self._run_simple(["devices"]))
        paired = {device.address for device in _parse_device_list(self._run_simple(["paired-devices"]))}
        resolved: list[BluetoothDevice] = []
        for device in devices:
            info = self._run_simple(["info", device.address], check=False)
            info_map = _parse_info(info)
            resolved.append(
                BluetoothDevice(
                    address=device.address,
                    name=info_map.get("Name") or device.name,
                    alias=info_map.get("Alias"),
                    paired=_truthy(info_map.get("Paired")) or device.address in paired,
                    trusted=_truthy(info_map.get("Trusted")),
                    connected=_truthy(info_map.get("Connected")),
                    blocked=_truthy(info_map.get("Blocked")),
                )
            )
        resolved.sort(key=lambda item: (not item.connected, not item.paired, item.name.casefold()))
        return resolved

    def scan(self, seconds: int = 8) -> dict[str, Any]:
        if not self.binary:
            raise RuntimeError("bluetoothctl nicht installiert")
        seconds = max(3, min(20, int(seconds)))
        with self._scan_lock:
            if self._scan_active:
                return {"ok": True, "message": "Bluetooth-Scan laeuft bereits"}
            self._scan_active = True
        thread = threading.Thread(target=self._scan_worker, args=(seconds,), daemon=True)
        thread.start()
        return {"ok": True, "message": f"Bluetooth-Scan fuer {seconds} Sekunden gestartet"}

    def pair_and_connect(self, address: str) -> dict[str, Any]:
        normalized = _normalize_address(address)
        commands = [
            "power on",
            "agent NoInputNoOutput",
            "default-agent",
            f"pair {normalized}",
            f"trust {normalized}",
            f"connect {normalized}",
            "quit",
        ]
        output = self._run_interactive(commands, timeout=45)
        return {"ok": True, "message": _pick_last_meaningful_line(output) or f"{normalized} gekoppelt"}

    def connect(self, address: str) -> dict[str, Any]:
        normalized = _normalize_address(address)
        output = self._run_interactive(["power on", f"connect {normalized}", "quit"], timeout=25)
        return {"ok": True, "message": _pick_last_meaningful_line(output) or f"{normalized} verbunden"}

    def disconnect(self, address: str) -> dict[str, Any]:
        normalized = _normalize_address(address)
        output = self._run_interactive([f"disconnect {normalized}", "quit"], timeout=20)
        return {"ok": True, "message": _pick_last_meaningful_line(output) or f"{normalized} getrennt"}

    def remove(self, address: str) -> dict[str, Any]:
        normalized = _normalize_address(address)
        output = self._run_interactive([f"remove {normalized}", "quit"], timeout=20)
        return {"ok": True, "message": _pick_last_meaningful_line(output) or f"{normalized} entfernt"}

    def _scan_worker(self, seconds: int) -> None:
        try:
            self._run_interactive(["power on", "scan on"], timeout=5)
            time.sleep(seconds)
            self._run_interactive(["scan off", "quit"], timeout=5)
        finally:
            with self._scan_lock:
                self._scan_active = False
                self._last_scan_finished_at = time.time()

    def _adapter_powered(self) -> bool:
        output = self._run_simple(["show"])
        info = _parse_info(output)
        return _truthy(info.get("Powered"))

    def _run_simple(self, args: list[str], *, check: bool = True) -> str:
        if not self.binary:
            raise RuntimeError("bluetoothctl nicht installiert")
        completed = subprocess.run(
            [self.binary, *args],
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
        output = (completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")
        if check and completed.returncode != 0:
            raise RuntimeError(output.strip() or f"bluetoothctl Fehler {completed.returncode}")
        return output

    def _run_interactive(self, commands: list[str], *, timeout: int) -> str:
        if not self.binary:
            raise RuntimeError("bluetoothctl nicht installiert")
        completed = subprocess.run(
            [self.binary],
            input="\n".join(commands) + "\n",
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        output = (completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")
        if completed.returncode != 0:
            raise RuntimeError(output.strip() or f"bluetoothctl Fehler {completed.returncode}")
        return output


@dataclass(frozen=True, slots=True)
class _SimpleDevice:
    address: str
    name: str


def _parse_device_list(text: str) -> list[_SimpleDevice]:
    devices: list[_SimpleDevice] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        match = DEVICE_RE.match(raw_line.strip())
        if not match:
            continue
        address = _normalize_address(match.group(1))
        if address in seen:
            continue
        seen.add(address)
        devices.append(_SimpleDevice(address=address, name=match.group(2).strip()))
    return devices


def _parse_info(text: str) -> dict[str, str]:
    info: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        info[key.strip()] = value.strip()
    return info


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().casefold() in {"yes", "true", "on"}


def _normalize_address(address: str) -> str:
    match = MAC_RE.search(address or "")
    if not match:
        raise ValueError("Ungueltige Bluetooth-Adresse")
    return match.group(1).upper()


def _pick_last_meaningful_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith("["):
            continue
        return line
    return ""
