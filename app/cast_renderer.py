from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

try:
    import pychromecast
    import zeroconf
    from pychromecast.discovery import CastBrowser, SimpleCastListener
except ImportError:  # pragma: no cover
    pychromecast = None
    zeroconf = None
    CastBrowser = None
    SimpleCastListener = None


@dataclass(frozen=True, slots=True)
class CastRenderer:
    id: str
    friendly_name: str
    host: str
    uuid: str

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "friendly_name": self.friendly_name,
            "host": self.host,
            "protocol": "Google Cast",
        }


class CastRendererService:
    """Google-Cast-Renderer über eine dauerhaft laufende Zeroconf-Discovery.

    pychromecast braucht eine *laufende* Zeroconf-Instanz, solange eine
    Verbindung zu einem Gerät besteht. Ein einmaliges ``get_chromecasts`` mit
    anschließendem ``stop_discovery`` führt deshalb beim späteren ``wait()`` zu
    ``AssertionError: Zeroconf instance loop must be running``. Wir halten den
    Browser darum für die gesamte Prozesslaufzeit offen.

    pychromecast ist **nicht** thread-sicher: der interne socket_client-Thread
    liest den SSL-Socket, und gleichzeitige Schreibzugriffe aus mehreren
    ``asyncio.to_thread``-Workern (Watchdog-Poll, Play, Lautstärke …) führen zu
    ``SSLV3_ALERT_BAD_RECORD_MAC`` und einem Verbindungsabriss. Deshalb wird
    **jede** Geräteoperation über ``self._lock`` serialisiert, und der Status
    wird passiv aus ``media_controller.status`` gelesen statt aktiv gepollt.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._zconf: Any = None
        self._browser: Any = None
        self._chromecasts: dict[str, Any] = {}
        self._connected: set[str] = set()
        self._started_at = 0.0
        self._start_browser()

    # -- interne Discovery -------------------------------------------------
    def _start_browser(self) -> None:
        if pychromecast is None or CastBrowser is None:
            return
        with self._lock:
            if self._browser is not None:
                return
            self._zconf = zeroconf.Zeroconf()
            self._browser = CastBrowser(SimpleCastListener(), self._zconf)
            self._browser.start_discovery()
            self._started_at = time.monotonic()

    def _devices(self) -> dict[Any, Any]:
        if self._browser is None:
            return {}
        return dict(self._browser.devices)

    def _wait_for_first_scan(self, timeout_seconds: float) -> None:
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        while time.monotonic() < deadline:
            if self._devices():
                return
            time.sleep(0.25)

    @staticmethod
    def _is_connected(cast: Any) -> bool:
        sc = getattr(cast, "socket_client", None)
        if sc is None:
            return False
        # is_connected kann während eines Reconnects kurz False sein; das ist
        # ok, wir behandeln nur den dauerhaft toten Fall separat.
        return bool(getattr(sc, "is_connected", False))

    # -- öffentliche API ------------------------------------------------------
    def list_renderers(self, *, force_refresh: bool = False, timeout_seconds: int = 4) -> list[CastRenderer]:
        if pychromecast is None or CastBrowser is None:
            return []
        self._start_browser()
        # Beim ersten Aufruf kurz auf die mDNS-Antworten warten.
        if force_refresh or (not self._devices() and time.monotonic() - self._started_at < 10):
            self._wait_for_first_scan(timeout_seconds)

        renderers: list[CastRenderer] = []
        for uuid, info in self._devices().items():
            uuid_str = str(uuid)
            host = ""
            try:
                host = str(info.host)
            except AttributeError:
                services = getattr(info, "services", None)
                if services:
                    host = str(next(iter(services)))
            renderers.append(
                CastRenderer(
                    id=f"cast:{uuid_str}",
                    friendly_name=str(getattr(info, "friendly_name", None) or "Google Cast"),
                    host=host,
                    uuid=uuid_str,
                )
            )
        renderers.sort(key=lambda item: (item.friendly_name.casefold(), item.host.casefold()))
        return renderers

    def discover(self, timeout_seconds: int = 5) -> dict[str, Any]:
        renderers = self.list_renderers(force_refresh=True, timeout_seconds=timeout_seconds)
        return {
            "available": pychromecast is not None,
            "message": f"{len(renderers)} Google-Cast-Gerät(e) gefunden" if renderers else "Keine Google-Cast-Geräte gefunden",
            "renderers": [renderer.to_public_dict() for renderer in renderers],
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

    def get_renderer(self, renderer_id: str) -> Any:
        if pychromecast is None:
            raise ValueError("pychromecast ist nicht installiert")
        self._start_browser()
        uuid_str = renderer_id.split(":", 1)[1] if ":" in renderer_id else renderer_id

        with self._lock:
            cast = self._chromecasts.get(renderer_id)

            # Dauerhaft tote Verbindung (socket_client-Thread gestoppt) wegwerfen
            # und neu aufbauen.
            if cast is not None:
                sc = getattr(cast, "socket_client", None)
                if sc is not None and getattr(sc, "is_stopped", False):
                    try:
                        cast.disconnect(blocking=False)
                    except Exception:  # pragma: no cover
                        pass
                    self._chromecasts.pop(renderer_id, None)
                    self._connected.discard(renderer_id)
                    cast = None

            if cast is None:
                info = None
                for uuid, candidate in self._devices().items():
                    if str(uuid) == uuid_str:
                        info = candidate
                        break
                if info is None:
                    self._wait_for_first_scan(5)
                    for uuid, candidate in self._devices().items():
                        if str(uuid) == uuid_str:
                            info = candidate
                            break
                if info is None:
                    raise ValueError("Google-Cast-Gerät nicht gefunden")
                cast = pychromecast.get_chromecast_from_cast_info(info, self._zconf)
                self._chromecasts[renderer_id] = cast

            if renderer_id not in self._connected:
                cast.wait(timeout=10)
                self._connected.add(renderer_id)
        return cast

    def _forget(self, renderer_id: str) -> None:
        with self._lock:
            self._connected.discard(renderer_id)
            cast = self._chromecasts.pop(renderer_id, None)
        if cast is not None:
            try:
                cast.disconnect(blocking=False)
            except Exception:  # pragma: no cover
                pass

    def set_volume(self, renderer_id: str, percent: int) -> int:
        with self._lock:
            cast = self.get_renderer(renderer_id)
            value = max(0, min(100, int(percent))) / 100
            cast.set_volume(value)
            return int(round(float(cast.status.volume_level or value) * 100))

    def get_volume(self, renderer_id: str) -> int:
        with self._lock:
            cast = self._chromecasts.get(renderer_id)
        if cast is None:
            return 0
        try:
            return int(round(float(cast.status.volume_level or 0) * 100))
        except Exception:  # noqa: BLE001
            return 0

    def set_mute(self, renderer_id: str, muted: bool) -> bool:
        with self._lock:
            cast = self.get_renderer(renderer_id)
            cast.set_volume_muted(bool(muted))
            return bool(cast.status.volume_muted)

    def get_mute(self, renderer_id: str) -> bool:
        with self._lock:
            cast = self._chromecasts.get(renderer_id)
        if cast is None:
            return False
        try:
            return bool(cast.status.volume_muted)
        except Exception:  # noqa: BLE001
            return False

    def get_transport_state(self, renderer_id: str) -> str:
        """Passiver Status - kein aktiver Poll auf den Socket.

        Der socket_client-Thread hält ``media_controller.status`` aktuell,
        solange die Verbindung steht. Nur bei tot gemeldeter Verbindung geben
        wir ``UNKNOWN`` zurück; ein aktives ``update_status()`` aus diesem
        Thread würde mit dem Lese-Thread kollidieren.
        """
        with self._lock:
            cast = self._chromecasts.get(renderer_id)
        if cast is None:
            return "UNKNOWN"
        sc = getattr(cast, "socket_client", None)
        if sc is not None and getattr(sc, "is_stopped", False):
            return "UNKNOWN"
        try:
            state = str(cast.media_controller.status.player_state or "IDLE").upper()
        except Exception:  # noqa: BLE001
            return "UNKNOWN"
        return "PLAYING" if state == "PLAYING" else state

    def play_stream(self, renderer_id: str, stream_url: str, *, title: str = "Radio Stream", artist: str = "") -> None:
        with self._lock:
            cast = self.get_renderer(renderer_id)
            media_controller = cast.media_controller

            current = str(getattr(media_controller.status, "player_state", "") or "").upper()
            if current in {"PLAYING", "BUFFERING", "PAUSED"}:
                try:
                    media_controller.stop()
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(1.0)

            media_controller.play_media(
                stream_url,
                "audio/mpeg",
                title=f"{title} - {artist}" if artist else title,
                stream_type="LIVE",
                autoplay=True,
            )
            try:
                media_controller.block_until_active(timeout=15)
            except Exception:  # noqa: BLE001
                pass

            # autoplay=True startet bereits; hier nur passiv bestätigen und
            # einmalig sanft nachhelfen, ohne den Socket zu pollen.
            deadline = time.monotonic() + 10
            nudged = False
            while time.monotonic() < deadline:
                state = str(getattr(media_controller.status, "player_state", "") or "").upper()
                if state == "PLAYING":
                    return
                if state in {"PAUSED", "IDLE"} and not nudged:
                    nudged = True
                    try:
                        media_controller.play()
                    except Exception:  # noqa: BLE001
                        pass
                time.sleep(1.0)

    def stop(self, renderer_id: str) -> None:
        with self._lock:
            cast = self.get_renderer(renderer_id)
            try:
                cast.media_controller.stop()
            except Exception:  # noqa: BLE001
                pass
