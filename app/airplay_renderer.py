from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

try:
    import pyatv
    from pyatv.interface import MediaMetadata
except ImportError:  # pragma: no cover
    pyatv = None
    MediaMetadata = None

logger = logging.getLogger(__name__)

# pyatv versucht bei jedem Stream, ID3-Tags aus dem (endlosen) Relay-Stream zu
# lesen; tinytag läuft dabei in einen Timeout und loggt einen kompletten
# Traceback. Wir übergeben eigene Metadaten - das ist also nur Lärm.
for _noisy in (
    "pyatv.support.metadata",
    "pyatv.protocols.raop.audio_source",
    # manche Netzwerkgeräte senden defekte mDNS-Pakete
    # ("An A record must have exactly 4 bytes"); zeroconf loggt das als Fehler,
    # verwirft das Paket aber folgenlos.
    "zeroconf",
):
    logging.getLogger(_noisy).setLevel(logging.CRITICAL)

_SCAN_CACHE_SECONDS = 120.0


@dataclass(frozen=True, slots=True)
class AirPlayRenderer:
    id: str
    friendly_name: str
    host: str
    identifier: str

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "friendly_name": self.friendly_name,
            "host": self.host,
            "protocol": "AirPlay",
        }


class AirPlayRendererService:
    """AirPlay-/RAOP-Wiedergabe über pyatv.

    Der Raspberry Pi holt den Sender-Stream (gute Leitung) und re-streamt ihn
    per RAOP an den Lautsprecher. RAOP puffert und fordert verlorene Pakete
    erneut an - deutlich robuster gegenüber schwachem WLAN des Zielgeräts als
    ein direkter Stream-Abruf durch das Gerät selbst.

    Quelle ist die lokale Relay-URL des Servers (``/upnp-stream/<station>``);
    pyatv kommt mit endlosen Icecast-URLs direkt nicht zuverlässig klar.

    Öffentliche Getter (``cached_renderers``, ``get_volume``, ``get_mute``,
    ``get_transport_state``) sind synchron, damit ``_build_audio_state`` sie aus
    einem Worker-Thread aufrufen kann. Alles, was pyatv-I/O macht, ist async.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._scan_cache: list[AirPlayRenderer] = []
        self._scan_cache_at = 0.0
        self._configs: dict[str, Any] = {}
        self._atv: Any = None
        self._atv_id: str | None = None
        self._stream_task: asyncio.Task[None] | None = None
        self._current_url: str | None = None
        self._muted = False
        self._last_volume = 0
        self._volume_before_mute = 30

    # -- Discovery (async) --------------------------------------------------
    async def _scan(self, timeout: int = 5) -> list[Any]:
        loop = asyncio.get_running_loop()
        try:
            return await pyatv.scan(loop, timeout=max(2, int(timeout)))
        except Exception as exc:  # noqa: BLE001
            logger.warning("AirPlay-Scan fehlgeschlagen: %s", exc)
            return []

    @staticmethod
    def _has_airplay(conf: Any) -> bool:
        for service in getattr(conf, "services", []):
            name = str(getattr(service, "protocol", "")).lower()
            if "airplay" in name or "raop" in name:
                return True
        return False

    async def list_renderers(self, *, force_refresh: bool = False, timeout_seconds: int = 5) -> list[AirPlayRenderer]:
        if pyatv is None:
            return []
        now = time.monotonic()
        if not force_refresh and self._scan_cache and now - self._scan_cache_at < _SCAN_CACHE_SECONDS:
            return list(self._scan_cache)

        renderers: dict[str, AirPlayRenderer] = {}
        attempts = 3 if force_refresh else 2
        for _ in range(attempts):
            for conf in await self._scan(timeout_seconds):
                if not self._has_airplay(conf):
                    continue
                identifier = str(conf.identifier or conf.name or "")
                if not identifier:
                    continue
                self._configs[identifier] = conf
                for alt in conf.all_identifiers:
                    self._configs[str(alt)] = conf
                renderers[identifier] = AirPlayRenderer(
                    id=f"airplay:{identifier}",
                    friendly_name=str(conf.name or "AirPlay"),
                    host=str(conf.address or ""),
                    identifier=identifier,
                )
            if renderers:
                break
            await asyncio.sleep(1.0)

        if renderers or force_refresh:
            self._scan_cache = sorted(
                renderers.values(), key=lambda item: item.friendly_name.casefold()
            )
            self._scan_cache_at = now
        return list(self._scan_cache)

    async def discover(self, timeout_seconds: int = 5) -> dict[str, Any]:
        renderers = await self.list_renderers(force_refresh=True, timeout_seconds=timeout_seconds)
        return {
            "available": pyatv is not None,
            "message": (
                f"{len(renderers)} AirPlay-Gerät(e) gefunden"
                if renderers
                else "Keine AirPlay-Geräte gefunden"
            ),
            "renderers": [renderer.to_public_dict() for renderer in renderers],
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

    # -- synchrone Getter ------------------------------------------------------
    def cached_renderers(self) -> list[AirPlayRenderer]:
        return list(self._scan_cache)

    def get_transport_state(self, renderer_id: str) -> str:
        task = self._stream_task
        if task is None or task.done():
            return "IDLE"
        return "PLAYING"

    def get_volume(self, renderer_id: str) -> int:
        atv = self._atv
        if atv is not None and self._atv_id == self._ident(renderer_id):
            try:
                vol = atv.audio.volume
                if vol is not None:
                    self._last_volume = int(round(float(vol)))
            except Exception:  # noqa: BLE001
                pass
        return int(self._last_volume)

    def get_mute(self, renderer_id: str) -> bool:
        return bool(self._muted)

    # -- Verbindung (async) -----------------------------------------------
    @staticmethod
    def _ident(renderer_id: str) -> str:
        return renderer_id.split(":", 1)[1] if renderer_id.startswith("airplay:") else renderer_id

    async def _get_config(self, identifier: str) -> Any:
        conf = self._configs.get(identifier)
        if conf is not None:
            return conf
        await self.list_renderers(force_refresh=True)
        conf = self._configs.get(identifier)
        if conf is None:
            raise ValueError("AirPlay-Gerät nicht gefunden")
        return conf

    async def _connect(self, identifier: str) -> Any:
        if self._atv is not None and self._atv_id == identifier:
            return self._atv
        await self._disconnect()
        conf = await self._get_config(identifier)
        loop = asyncio.get_running_loop()
        self._atv = await pyatv.connect(conf, loop)
        self._atv_id = identifier
        return self._atv

    async def _disconnect(self) -> None:
        atv = self._atv
        self._atv = None
        self._atv_id = None
        if atv is not None:
            try:
                atv.close()
            except Exception:  # noqa: BLE001
                pass

    async def _cancel_stream(self) -> None:
        task = self._stream_task
        self._stream_task = None
        self._current_url = None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    # -- Wiedergabe (async) ---------------------------------------------
    async def play_stream(
        self, renderer_id: str, stream_url: str, *, title: str = "Radio Stream", artist: str = ""
    ) -> None:
        if pyatv is None:
            raise RuntimeError("pyatv ist nicht installiert")
        identifier = self._ident(renderer_id)
        async with self._lock:
            await self._cancel_stream()
            atv = await self._connect(identifier)

            metadata = None
            if MediaMetadata is not None:
                metadata = MediaMetadata(
                    title=title or "Radio", artist=artist or None, album="onradio"
                )

            self._current_url = stream_url
            self._stream_task = asyncio.get_running_loop().create_task(
                self._run_stream(atv, stream_url, metadata)
            )
            await asyncio.sleep(0.5)

    async def _run_stream(self, atv: Any, url: str, metadata: Any) -> None:
        """Hält den RAOP-Stream am Leben.

        ``stream_file`` kehrt zurück, sobald der HTTP-Quellstream kurz stockt
        (Relay verbindet upstream neu). Wir starten sofort neu, damit der Ton
        durchläuft. Erst bei mehreren Sofort-Fehlern in Folge geben wir auf und
        überlassen die Wiederherstellung dem Watchdog.
        """
        quick_failures = 0
        while True:
            started = time.monotonic()
            try:
                await atv.stream.stream_file(url, metadata=metadata)
                reason = "regulär beendet"
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                reason = f"Fehler: {exc}"
            ran = time.monotonic() - started
            if ran < 6.0:
                quick_failures += 1
                if quick_failures >= 4:
                    logger.warning(
                        "AirPlay-Stream bricht sofort ab (%s) - Watchdog übernimmt", reason
                    )
                    return
            else:
                quick_failures = 0
            logger.info("AirPlay-Stream nach %.0fs neu gestartet (%s)", ran, reason)
            await asyncio.sleep(1.0)

    async def stop(self, renderer_id: str) -> None:
        async with self._lock:
            await self._cancel_stream()
            await self._disconnect()

    async def reset(self) -> None:
        async with self._lock:
            await self._cancel_stream()
            await self._disconnect()
            self._configs.clear()
            self._scan_cache = []
            self._scan_cache_at = 0.0

    # -- Lautstärke (async) -------------------------------------------------
    async def set_volume(self, renderer_id: str, percent: int) -> int:
        async with self._lock:
            atv = await self._connect(self._ident(renderer_id))
        value = float(max(0, min(100, int(percent))))
        try:
            await atv.audio.set_volume(value)
        except Exception as exc:  # noqa: BLE001
            logger.warning("AirPlay-Lautstärke setzen fehlgeschlagen: %s", exc)
        self._last_volume = int(round(value))
        self._muted = value == 0
        return self._last_volume

    async def set_mute(self, renderer_id: str, muted: bool) -> bool:
        async with self._lock:
            atv = await self._connect(self._ident(renderer_id))
        if muted and not self._muted:
            self._volume_before_mute = self._last_volume or 30
            try:
                await atv.audio.set_volume(0.0)
            except Exception:  # noqa: BLE001
                pass
            self._last_volume = 0
            self._muted = True
        elif not muted and self._muted:
            try:
                await atv.audio.set_volume(float(self._volume_before_mute))
            except Exception:  # noqa: BLE001
                pass
            self._last_volume = self._volume_before_mute
            self._muted = False
        return self._muted
