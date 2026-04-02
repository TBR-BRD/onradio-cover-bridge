from __future__ import annotations

import socket
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET

import requests

from .settings import settings

SSDP_MULTICAST_HOST = "239.255.255.250"
SSDP_PORT = 1900
MEDIA_RENDERER_ST = "urn:schemas-upnp-org:device:MediaRenderer:1"
AV_TRANSPORT_SERVICE = "urn:schemas-upnp-org:service:AVTransport:1"
RENDERING_CONTROL_SERVICE = "urn:schemas-upnp-org:service:RenderingControl:1"

CONTENT_TYPE_BY_SUFFIX = {
    ".aac": "audio/aac",
    ".aacp": "audio/aac",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".mp4": "audio/mp4",
    ".oga": "audio/ogg",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".wav": "audio/wav",
}

FALLBACK_METADATA_MIME_TYPES = (
    "audio/mpeg",
    "audio/aac",
    "audio/flac",
    "audio/ogg",
)


@dataclass(frozen=True, slots=True)
class UpnpRenderer:
    id: str
    udn: str
    friendly_name: str
    location: str
    host: str
    av_transport_url: str | None
    av_transport_type: str | None
    rendering_control_url: str | None
    rendering_control_type: str | None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "udn": self.udn,
            "friendly_name": self.friendly_name,
            "location": self.location,
            "host": self.host,
        }


class UpnpSoapError(RuntimeError):
    def __init__(
        self,
        *,
        action: str,
        control_url: str,
        status_code: int | None,
        error_code: str | None = None,
        error_description: str | None = None,
        raw_detail: str | None = None,
    ) -> None:
        self.action = action
        self.control_url = control_url
        self.status_code = status_code
        self.error_code = str(error_code).strip() if error_code is not None else None
        self.error_description = (error_description or "").strip() or None
        self.raw_detail = (raw_detail or "").strip() or None
        super().__init__(self._build_message())

    def _build_message(self) -> str:
        detail = _friendly_fault_detail(self.error_code, self.error_description, self.raw_detail)
        if detail:
            return f"UPnP {self.action}: {detail}"
        if self.status_code:
            return f"UPnP {self.action} fehlgeschlagen (HTTP {self.status_code})"
        return f"UPnP {self.action} fehlgeschlagen"


class UpnpRendererService:
    def __init__(self) -> None:
        self._cache: dict[str, UpnpRenderer] = {}
        self._cache_expires_at = 0.0
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": settings.user_agent})

    def list_renderers(self, *, force_refresh: bool = False, timeout_seconds: int = 3) -> list[UpnpRenderer]:
        if not force_refresh and self._cache and time.monotonic() < self._cache_expires_at:
            return list(self._cache.values())

        discovered = self._discover(timeout_seconds=max(1, int(timeout_seconds)))
        self._cache = {renderer.id: renderer for renderer in discovered}
        self._cache_expires_at = time.monotonic() + max(10, settings.upnp_discovery_cache_seconds)
        return list(discovered)

    def discover(self, timeout_seconds: int = 4) -> dict[str, Any]:
        renderers = self.list_renderers(force_refresh=True, timeout_seconds=timeout_seconds)
        return {
            "available": True,
            "message": f"{len(renderers)} WLAN-Lautsprecher gefunden" if renderers else "Keine WLAN-Lautsprecher gefunden",
            "renderers": [renderer.to_public_dict() for renderer in renderers],
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

    def status(self) -> dict[str, Any]:
        try:
            renderers = self.list_renderers(force_refresh=False, timeout_seconds=2)
        except Exception as exc:  # noqa: BLE001
            return {
                "available": False,
                "message": str(exc),
                "renderers": [],
                "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
        return {
            "available": True,
            "message": f"{len(renderers)} WLAN-Lautsprecher bekannt" if renderers else "Noch kein WLAN-Lautsprecher gefunden",
            "renderers": [renderer.to_public_dict() for renderer in renderers],
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

    def get_renderer(self, renderer_id: str) -> UpnpRenderer:
        normalized = self._normalize_renderer_id(renderer_id)
        renderers = self.list_renderers(force_refresh=False, timeout_seconds=2)
        for renderer in renderers:
            if self._normalize_renderer_id(renderer.id) == normalized or self._normalize_renderer_id(renderer.udn) == normalized:
                return renderer
        renderers = self.list_renderers(force_refresh=True, timeout_seconds=4)
        for renderer in renderers:
            if self._normalize_renderer_id(renderer.id) == normalized or self._normalize_renderer_id(renderer.udn) == normalized:
                return renderer
        raise ValueError("WLAN-Lautsprecher nicht gefunden")

    def get_volume(self, renderer_id: str) -> int | None:
        renderer = self.get_renderer(renderer_id)
        if not renderer.rendering_control_url or not renderer.rendering_control_type:
            return None
        xml_root = self._soap_action(
            renderer.rendering_control_url,
            renderer.rendering_control_type,
            "GetVolume",
            {"InstanceID": 0, "Channel": "Master"},
        )
        value = _find_text(xml_root, ".//{*}CurrentVolume")
        if value is None:
            return None
        try:
            return max(0, min(100, int(float(value))))
        except ValueError:
            return None

    def set_volume(self, renderer_id: str, percent: int) -> int | None:
        renderer = self.get_renderer(renderer_id)
        if not renderer.rendering_control_url or not renderer.rendering_control_type:
            raise RuntimeError("Lautstärke wird von diesem WLAN-Lautsprecher nicht unterstützt")
        volume = max(0, min(100, int(percent)))
        self._soap_action(
            renderer.rendering_control_url,
            renderer.rendering_control_type,
            "SetVolume",
            {"InstanceID": 0, "Channel": "Master", "DesiredVolume": volume},
        )
        return self.get_volume(renderer_id)

    def get_mute(self, renderer_id: str) -> bool | None:
        renderer = self.get_renderer(renderer_id)
        if not renderer.rendering_control_url or not renderer.rendering_control_type:
            return None
        xml_root = self._soap_action(
            renderer.rendering_control_url,
            renderer.rendering_control_type,
            "GetMute",
            {"InstanceID": 0, "Channel": "Master"},
        )
        value = _find_text(xml_root, ".//{*}CurrentMute")
        if value is None:
            return None
        return str(value).strip() in {"1", "true", "True", "yes", "on"}

    def set_mute(self, renderer_id: str, muted: bool) -> bool | None:
        renderer = self.get_renderer(renderer_id)
        if not renderer.rendering_control_url or not renderer.rendering_control_type:
            raise RuntimeError("Stummschaltung wird von diesem WLAN-Lautsprecher nicht unterstützt")
        self._soap_action(
            renderer.rendering_control_url,
            renderer.rendering_control_type,
            "SetMute",
            {"InstanceID": 0, "Channel": "Master", "DesiredMute": 1 if muted else 0},
        )
        return self.get_mute(renderer_id)

    def get_transport_state(self, renderer_id: str) -> str | None:
        renderer = self.get_renderer(renderer_id)
        if not renderer.av_transport_url or not renderer.av_transport_type:
            return None
        xml_root = self._soap_action(
            renderer.av_transport_url,
            renderer.av_transport_type,
            "GetTransportInfo",
            {"InstanceID": 0},
        )
        return _find_text(xml_root, ".//{*}CurrentTransportState")

    def play_stream(
        self,
        renderer_id: str,
        stream_url: str,
        *,
        source_probe_url: str | None = None,
        title: str = "Radio Stream",
        artist: str = "",
        station_name: str = "",
    ) -> dict[str, Any]:
        renderer = self.get_renderer(renderer_id)
        if not renderer.av_transport_url or not renderer.av_transport_type:
            raise RuntimeError("Wiedergabe wird von diesem WLAN-Lautsprecher nicht unterstützt")

        try:
            self.stop(renderer_id)
        except Exception:
            pass

        metadata_candidates = _build_metadata_candidates(
            stream_url=stream_url,
            probe_url=source_probe_url or stream_url,
            title=title,
            artist=artist,
            station_name=station_name,
        )

        last_error: Exception | None = None
        for metadata in metadata_candidates:
            try:
                self._soap_action(
                    renderer.av_transport_url,
                    renderer.av_transport_type,
                    "SetAVTransportURI",
                    {
                        "InstanceID": 0,
                        "CurrentURI": stream_url,
                        "CurrentURIMetaData": metadata,
                    },
                )
                time.sleep(0.15)
                self._soap_action(
                    renderer.av_transport_url,
                    renderer.av_transport_type,
                    "Play",
                    {"InstanceID": 0, "Speed": "1"},
                )
                return {
                    "ok": True,
                    "renderer": renderer.to_public_dict(),
                    "transport_state": self.get_transport_state(renderer_id) or "PLAYING",
                }
            except UpnpSoapError as exc:
                last_error = exc
                if exc.action == "SetAVTransportURI":
                    continue
                raise RuntimeError(_friendly_play_error(renderer, exc)) from exc
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                break

        if last_error is not None:
            raise RuntimeError(_friendly_play_error(renderer, last_error)) from last_error
        raise RuntimeError(f"{renderer.friendly_name} konnte den Stream nicht starten")

    def stop(self, renderer_id: str) -> dict[str, Any]:
        renderer = self.get_renderer(renderer_id)
        if not renderer.av_transport_url or not renderer.av_transport_type:
            raise RuntimeError("Stopp wird von diesem WLAN-Lautsprecher nicht unterstützt")
        self._soap_action(
            renderer.av_transport_url,
            renderer.av_transport_type,
            "Stop",
            {"InstanceID": 0},
        )
        return {
            "ok": True,
            "renderer": renderer.to_public_dict(),
            "transport_state": self.get_transport_state(renderer_id) or "STOPPED",
        }

    def _discover(self, timeout_seconds: int) -> list[UpnpRenderer]:
        locations: dict[str, None] = {}
        payload = (
            "M-SEARCH * HTTP/1.1\r\n"
            f"HOST: {SSDP_MULTICAST_HOST}:{SSDP_PORT}\r\n"
            'MAN: "ssdp:discover"\r\n'
            f"MX: {max(1, min(5, timeout_seconds))}\r\n"
            f"ST: {MEDIA_RENDERER_ST}\r\n"
            "USER-AGENT: onradio-cover-bridge/1.0 UPnP/1.1 Python/3\r\n"
            "\r\n"
        ).encode("utf-8")

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        try:
            sock.settimeout(0.5)
            try:
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            except OSError:
                pass
            for _ in range(2):
                sock.sendto(payload, (SSDP_MULTICAST_HOST, SSDP_PORT))

            deadline = time.monotonic() + max(1.0, float(timeout_seconds))
            while time.monotonic() < deadline:
                try:
                    data, _addr = sock.recvfrom(65535)
                except socket.timeout:
                    continue
                headers = _parse_ssdp_response(data)
                location = headers.get("location")
                if location:
                    locations[location] = None
        finally:
            sock.close()

        renderers: list[UpnpRenderer] = []
        for location in locations:
            try:
                renderer = self._fetch_renderer_description(location)
            except Exception:
                continue
            if renderer is not None:
                renderers.append(renderer)

        renderers.sort(key=lambda item: (item.friendly_name.casefold(), item.host.casefold()))
        return renderers

    def _fetch_renderer_description(self, location: str) -> UpnpRenderer | None:
        response = self._session.get(
            location,
            timeout=settings.upnp_request_timeout_seconds,
        )
        response.raise_for_status()
        xml_root = ET.fromstring(response.content)

        base_url = (_find_text(xml_root, ".//{*}URLBase") or _base_url(location)).strip() or _base_url(location)
        device = _find_media_renderer_device(xml_root)
        if device is None:
            return None

        friendly_name = (_find_text(device, "./{*}friendlyName") or "WLAN-Lautsprecher").strip()
        udn = (_find_text(device, "./{*}UDN") or location).strip()
        av_transport = _find_service(device, "AVTransport")
        rendering_control = _find_service(device, "RenderingControl")

        parsed = urlparse(location)
        host = parsed.hostname or friendly_name
        return UpnpRenderer(
            id=f"upnp:{_normalize_identifier(udn)}",
            udn=udn,
            friendly_name=friendly_name,
            location=location,
            host=host,
            av_transport_url=urljoin(base_url, av_transport[1]) if av_transport else None,
            av_transport_type=av_transport[0] if av_transport else None,
            rendering_control_url=urljoin(base_url, rendering_control[1]) if rendering_control else None,
            rendering_control_type=rendering_control[0] if rendering_control else None,
        )

    def _soap_action(self, control_url: str, service_type: str, action: str, arguments: dict[str, Any]) -> ET.Element:
        envelope = _build_soap_envelope(service_type=service_type, action=action, arguments=arguments)
        response = self._session.post(
            control_url,
            data=envelope.encode("utf-8"),
            timeout=settings.upnp_request_timeout_seconds,
            headers={
                "Content-Type": 'text/xml; charset="utf-8"',
                "SOAPAction": f'"{service_type}#{action}"',
            },
        )

        xml_root = _safe_xml_root(response.content)
        fault = _extract_soap_fault(xml_root) if xml_root is not None else None
        if response.status_code >= 400 or fault is not None:
            raise UpnpSoapError(
                action=action,
                control_url=control_url,
                status_code=response.status_code,
                error_code=(fault or {}).get("error_code"),
                error_description=(fault or {}).get("error_description"),
                raw_detail=response.text[:240] if response.text else None,
            )

        if xml_root is None:
            raise RuntimeError(f"UPnP {action} lieferte keine gültige XML-Antwort")
        return xml_root

    @staticmethod
    def _normalize_renderer_id(value: str) -> str:
        normalized = str(value or "").strip().casefold()
        if normalized.startswith("upnp:"):
            normalized = normalized[5:]
        return normalized


def _parse_ssdp_response(data: bytes) -> dict[str, str]:
    text = data.decode("utf-8", errors="ignore")
    headers: dict[str, str] = {}
    for line in text.splitlines()[1:]:
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        headers[key.strip().casefold()] = value.strip()
    return headers


def _base_url(location: str) -> str:
    parsed = urlparse(location)
    return f"{parsed.scheme}://{parsed.netloc}/"


def _find_text(element: ET.Element, query: str) -> str | None:
    found = element.find(query)
    if found is None or found.text is None:
        return None
    return found.text.strip() or None


def _find_media_renderer_device(xml_root: ET.Element) -> ET.Element | None:
    for device in xml_root.findall(".//{*}device"):
        device_type = (_find_text(device, "./{*}deviceType") or "").strip()
        if "MediaRenderer" in device_type:
            return device
    return None


def _find_service(device: ET.Element, service_name: str) -> tuple[str, str] | None:
    for service in device.findall(".//{*}service"):
        service_type = (_find_text(service, "./{*}serviceType") or "").strip()
        if service_name not in service_type:
            continue
        control_url = (_find_text(service, "./{*}controlURL") or "").strip()
        if not control_url:
            continue
        return service_type, control_url
    return None


def _normalize_identifier(value: str) -> str:
    keep = []
    for char in str(value or "").strip().casefold():
        if char.isalnum():
            keep.append(char)
        elif char in {"-", "_"}:
            keep.append(char)
    return "".join(keep) or "renderer"


def _xml_escape(value: Any) -> str:
    text = str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _build_soap_envelope(*, service_type: str, action: str, arguments: dict[str, Any]) -> str:
    parts = []
    for key, value in arguments.items():
        parts.append(f"<{key}>{_xml_escape(value)}</{key}>")
    arguments_xml = "".join(parts)
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
        's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        '<s:Body>'
        f'<u:{action} xmlns:u="{_xml_escape(service_type)}">{arguments_xml}</u:{action}>'
        '</s:Body>'
        '</s:Envelope>'
    )


def _safe_xml_root(content: bytes | None) -> ET.Element | None:
    if not content:
        return None
    try:
        return ET.fromstring(content)
    except ET.ParseError:
        return None


def _extract_soap_fault(xml_root: ET.Element | None) -> dict[str, str] | None:
    if xml_root is None:
        return None
    fault = xml_root.find(".//{*}Fault")
    if fault is None:
        return None
    return {
        "error_code": _find_text(fault, ".//{*}errorCode") or _find_text(fault, ".//errorCode") or "",
        "error_description": _find_text(fault, ".//{*}errorDescription") or _find_text(fault, ".//errorDescription") or "",
    }


def _friendly_fault_detail(error_code: str | None, error_description: str | None, raw_detail: str | None) -> str:
    code = (error_code or "").strip()
    description = (error_description or "").strip()
    description_lower = description.casefold()
    if code == "714" or "mime" in description_lower:
        return "Der Lautsprecher lehnt das Stream-Format ab"
    if code == "701":
        return "Der Stream konnte vom Lautsprecher nicht gefunden oder geöffnet werden"
    if code == "702":
        return "Der Lautsprecher blockiert den Stream im Moment"
    if code == "716":
        return "Der Lautsprecher akzeptiert diese Stream-Adresse nicht"
    if code == "718":
        return "Der Lautsprecher meldet eine ungültige Wiedergabeinstanz"
    if description:
        return description
    if raw_detail:
        compact = " ".join(raw_detail.split())
        return compact[:180]
    return ""


def _friendly_play_error(renderer: UpnpRenderer, error: Exception) -> str:
    if isinstance(error, UpnpSoapError):
        suffix = _friendly_fault_detail(error.error_code, error.error_description, error.raw_detail)
        if suffix:
            return f"{renderer.friendly_name}: {suffix}."
        return f"{renderer.friendly_name}: UPnP-Wiedergabe konnte nicht gestartet werden."
    return f"{renderer.friendly_name}: {error}"


def _build_metadata_candidates(*, stream_url: str, probe_url: str, title: str, artist: str, station_name: str) -> list[str]:
    guessed = _probe_stream_content_type(probe_url)
    mime_candidates: list[str] = []
    if guessed:
        mime_candidates.append(guessed)
    mime_candidates.extend(FALLBACK_METADATA_MIME_TYPES)

    candidates = [""]
    seen_metadata = {""}
    for mime_type in mime_candidates:
        for item_class in ("object.item.audioItem.audioBroadcast", "object.item.audioItem.musicTrack"):
            metadata = _build_didl_metadata(
                stream_url=stream_url,
                title=title,
                artist=artist,
                station_name=station_name,
                mime_type=mime_type,
                item_class=item_class,
            )
            if metadata not in seen_metadata:
                candidates.append(metadata)
                seen_metadata.add(metadata)
    return candidates


def _probe_stream_content_type(url: str) -> str | None:
    guessed = _content_type_from_url(url)
    if guessed:
        return guessed

    for method in ("HEAD", "GET"):
        try:
            if method == "HEAD":
                response = requests.head(
                    url,
                    allow_redirects=True,
                    timeout=(3, 5),
                    headers={"User-Agent": settings.user_agent},
                )
            else:
                response = requests.get(
                    url,
                    allow_redirects=True,
                    stream=True,
                    timeout=(3, 5),
                    headers={"User-Agent": settings.user_agent},
                )
            response.raise_for_status()
            content_type = _clean_content_type(response.headers.get("Content-Type"))
            response.close()
            if content_type:
                return content_type
        except Exception:
            continue
    return None


def _content_type_from_url(url: str) -> str | None:
    path = urlparse(url).path or ""
    lowered = path.casefold()
    for suffix, content_type in CONTENT_TYPE_BY_SUFFIX.items():
        if lowered.endswith(suffix):
            return content_type
    return None


def _clean_content_type(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.split(";", 1)[0].strip().casefold()
    if not cleaned:
        return None
    if cleaned in {"application/octet-stream", "binary/octet-stream"}:
        return None
    if cleaned.startswith("audio/"):
        if cleaned == "audio/aacp":
            return "audio/aac"
        return cleaned
    return None


def _build_didl_metadata(*, stream_url: str, title: str, artist: str, station_name: str, mime_type: str, item_class: str) -> str:
    safe_title = title or station_name or "Radio Stream"
    safe_station = station_name or "Radio"
    safe_artist = artist or safe_station
    safe_mime = _clean_content_type(mime_type) or "audio/mpeg"
    return (
        '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" '
        'xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
        '<item id="0" parentID="0" restricted="0">'
        f'<dc:title>{_xml_escape(safe_title)}</dc:title>'
        f'<dc:creator>{_xml_escape(safe_artist)}</dc:creator>'
        f'<upnp:artist>{_xml_escape(safe_artist)}</upnp:artist>'
        f'<upnp:album>{_xml_escape(safe_station)}</upnp:album>'
        f'<upnp:class>{_xml_escape(item_class)}</upnp:class>'
        f'<res protocolInfo="http-get:*:{_xml_escape(safe_mime)}:*">{_xml_escape(stream_url)}</res>'
        '</item>'
        '</DIDL-Lite>'
    )
