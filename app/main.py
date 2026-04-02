from __future__ import annotations

import asyncio
import io
import ipaddress
import json
import logging
import os
import shlex
import requests
import shutil
import socket
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

try:
    import qrcode
    from qrcode.constants import ERROR_CORRECT_M
    from qrcode.image.svg import SvgPathImage
except ImportError:  # pragma: no cover
    qrcode = None
    ERROR_CORRECT_M = None
    SvgPathImage = None

from .audio_resolver import AudioStreamResolver
from .audio_system import AudioOutput, AudioState, AudioSystemService
from .config_manager import ConfigRepository, ControllerConfig
from .cover_provider import PreferredCoverProvider
from .display_schedule import DisplayScheduleService
from .playlist_fetcher import PlaylistFetcher
from .selftest_service import SelfTestService
from .settings import settings
from .state import SharedState, StateRepository
from .stations import STATIONS, STATION_MAP
from .update_service import UpdateService
from .upnp_renderer import UpnpRendererService
from .weather_service import WeatherService

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
logger = logging.getLogger("onradio_cover_bridge")
QR_CODE_AVAILABLE = qrcode is not None and SvgPathImage is not None and settings.display_controller_qr_enabled


class StationSelection(BaseModel):
    station_id: str


class PlaybackState(BaseModel):
    playing: bool


class AudioVolumePayload(BaseModel):
    percent: int = Field(..., ge=0, le=100)


class AudioVolumeDeltaPayload(BaseModel):
    delta: int = Field(..., ge=-100, le=100)


class AudioOutputPayload(BaseModel):
    output_id: str


class MutePayload(BaseModel):
    muted: bool


class OutputPlaybackPayload(BaseModel):
    playing: bool


class UpnpDiscoveryPayload(BaseModel):
    seconds: int = Field(default=4, ge=2, le=12)


class ConfigUpdatePayload(BaseModel):
    display_schedule_enabled: bool | None = None
    display_on_hour: int | None = Field(default=None, ge=0, le=23)
    display_off_hour: int | None = Field(default=None, ge=0, le=23)
    transitions_enabled: bool | None = None
    update_source_zip_url: str | None = None


class AppServices:
    def __init__(self) -> None:
        self.repository = StateRepository()
        self.config_repository = ConfigRepository()
        self.state: SharedState = self.repository.load()
        self.config: ControllerConfig = self.config_repository.load()
        self.state_lock = asyncio.Lock()
        self.config_lock = asyncio.Lock()
        self.refresh_lock = asyncio.Lock()
        self.playlist_fetcher = PlaylistFetcher()
        self.cover_provider = PreferredCoverProvider()
        self.audio_resolver = AudioStreamResolver()
        self.audio_service = AudioSystemService()
        self.upnp_service = UpnpRendererService()
        self.weather_service = WeatherService()
        self.display_schedule = DisplayScheduleService()
        self.selftest_service = SelfTestService(
            playlist_fetcher=self.playlist_fetcher,
            audio_resolver=self.audio_resolver,
            weather_service=self.weather_service,
            audio_service=self.audio_service,
            upnp_service=self.upnp_service,
        )
        self.update_service = UpdateService(PROJECT_DIR)
        self.poll_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        await asyncio.to_thread(self._ensure_configured_output_applied)
        self.poll_task = asyncio.create_task(self._poll_loop(), name="playlist-poll-loop")
        await self.refresh_selected_station()

    async def stop(self) -> None:
        if self.poll_task is None:
            return
        self.poll_task.cancel()
        try:
            await self.poll_task
        except asyncio.CancelledError:
            pass

    async def snapshot(self) -> dict[str, Any]:
        async with self.state_lock:
            payload = self.state.to_public_dict()
        async with self.config_lock:
            config_copy = ControllerConfig(**self.config.to_public_dict())
            config_public = config_copy.to_public_dict()
            display_schedule = self.display_schedule.current_state(config_copy).to_public_dict()
            configured_update_url = config_copy.update_source_zip_url

        controller_url = _build_controller_url()
        payload["controller_url"] = controller_url
        payload["controller_host"] = _controller_host_label(controller_url)
        payload["display_url"] = _build_display_url(controller_url)
        payload["display_host"] = _controller_host_label(payload["display_url"])
        payload["controller_qr_enabled"] = QR_CODE_AVAILABLE
        payload["config"] = config_public
        payload["display_schedule"] = display_schedule
        payload["app_version"] = settings.app_version

        try:
            payload["display_weather"] = await asyncio.to_thread(self.weather_service.get_display_weather)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Weather refresh failed: %s", exc)
            payload["display_weather"] = {
                "location": settings.weather_location_name,
                "days": [],
                "error": str(exc),
            }

        try:
            payload["local_audio"] = (await asyncio.to_thread(self._build_audio_state, config_copy)).to_public_dict()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Audio state refresh failed: %s", exc)
            payload["local_audio"] = {
                "available": False,
                "backend": "error",
                "volume_percent": 0,
                "muted": False,
                "outputs": [],
                "selected_output_id": None,
                "selected_output_label": None,
                "message": str(exc),
                "route_kind": "local",
                "supports_transport": False,
                "transport_playing": False,
            }

        payload["upnp_status"] = await asyncio.to_thread(self._build_upnp_status, config_copy)
        payload["update_status"] = await asyncio.to_thread(self.update_service.status, configured_update_url)
        return payload

    async def select_station(self, station_id: str) -> dict[str, Any]:
        if station_id not in STATION_MAP:
            raise KeyError(station_id)

        was_upnp_playing = False
        async with self.config_lock:
            config_copy = ControllerConfig(**self.config.to_public_dict())
        try:
            audio_state = await asyncio.to_thread(self._build_audio_state, config_copy)
            was_upnp_playing = audio_state.route_kind == "upnp" and audio_state.transport_playing
        except Exception:
            was_upnp_playing = False

        async with self.state_lock:
            self.state.set_selected_station(station_id)
            self.repository.save(self.state)

        await self.refresh_selected_station()

        if was_upnp_playing:
            try:
                await self.set_output_playback(True)
            except Exception as exc:  # noqa: BLE001
                logger.warning("UPnP retune failed for %s: %s", station_id, exc)
        return await self.snapshot()

    async def select_relative_station(self, step: int) -> dict[str, Any]:
        async with self.state_lock:
            current_id = self.state.selected_station_id
        ids = [station.id for station in STATIONS]
        try:
            index = ids.index(current_id)
        except ValueError:
            index = 0
        new_id = ids[(index + step) % len(ids)]
        return await self.select_station(new_id)

    async def set_playback(self, playing: bool) -> dict[str, Any]:
        async with self.state_lock:
            self.state.set_playing_hint(playing)
            self.repository.save(self.state)
        return await self.snapshot()

    async def refresh_selected_station(self) -> dict[str, Any]:
        async with self.refresh_lock:
            station = STATION_MAP[(await self._get_selected_station_id())]
            try:
                now_playing = await asyncio.to_thread(self.playlist_fetcher.fetch, station)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Metadata refresh failed for %s: %s", station.name, exc)
                async with self.state_lock:
                    self.state.set_error(str(exc))
                    self.repository.save(self.state)
                return await self.snapshot()

            cover_result = None
            try:
                cover_result = await asyncio.to_thread(self.cover_provider.find_cover, station, now_playing)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Cover lookup failed for %s | %s - %s: %s",
                    station.name,
                    now_playing.artist,
                    now_playing.title,
                    exc,
                )

            proxied_cover_url = self._to_local_cover_url(cover_result.url) if cover_result else None
            async with self.state_lock:
                self.state.set_track(
                    played_at=now_playing.played_at,
                    artist=now_playing.artist,
                    title=now_playing.title,
                    cover_url=proxied_cover_url,
                    cover_source=cover_result.source if cover_result else None,
                )
                self.repository.save(self.state)
        return await self.snapshot()

    async def resolve_station_stream(self, station_id: str) -> str:
        if station_id not in STATION_MAP:
            raise KeyError(station_id)
        station = STATION_MAP[station_id]
        return await asyncio.to_thread(self.audio_resolver.resolve, station)

    async def get_cover_payload(self, url: str):
        return await asyncio.to_thread(self.cover_provider.fetch_image_payload, url)

    async def get_audio_state(self) -> dict[str, Any]:
        async with self.config_lock:
            config_copy = ControllerConfig(**self.config.to_public_dict())
        return (await asyncio.to_thread(self._build_audio_state, config_copy)).to_public_dict()

    async def set_audio_volume(self, percent: int) -> dict[str, Any]:
        async with self.config_lock:
            config_copy = ControllerConfig(**self.config.to_public_dict())
        if config_copy.audio_output_id.startswith("upnp:"):
            await asyncio.to_thread(self.upnp_service.set_volume, config_copy.audio_output_id, percent)
            return await self.get_audio_state()
        await asyncio.to_thread(self.audio_service.set_volume, percent)
        return await self.get_audio_state()

    async def change_audio_volume(self, delta: int) -> dict[str, Any]:
        async with self.config_lock:
            config_copy = ControllerConfig(**self.config.to_public_dict())
        if config_copy.audio_output_id.startswith("upnp:"):
            current = await asyncio.to_thread(self._build_audio_state, config_copy)
            target = max(0, min(100, int(current.volume_percent) + int(delta)))
            await asyncio.to_thread(self.upnp_service.set_volume, config_copy.audio_output_id, target)
            return await self.get_audio_state()
        await asyncio.to_thread(self.audio_service.change_volume, delta)
        return await self.get_audio_state()

    async def set_audio_muted(self, muted: bool) -> dict[str, Any]:
        async with self.config_lock:
            config_copy = ControllerConfig(**self.config.to_public_dict())
        if config_copy.audio_output_id.startswith("upnp:"):
            await asyncio.to_thread(self.upnp_service.set_mute, config_copy.audio_output_id, muted)
            return await self.get_audio_state()
        await asyncio.to_thread(self.audio_service.set_muted, muted)
        return await self.get_audio_state()

    async def toggle_audio_mute(self) -> dict[str, Any]:
        async with self.config_lock:
            config_copy = ControllerConfig(**self.config.to_public_dict())
        if config_copy.audio_output_id.startswith("upnp:"):
            current = await asyncio.to_thread(self._build_audio_state, config_copy)
            await asyncio.to_thread(self.upnp_service.set_mute, config_copy.audio_output_id, not current.muted)
            return await self.get_audio_state()
        await asyncio.to_thread(self.audio_service.toggle_mute)
        return await self.get_audio_state()

    async def set_audio_output(self, output_id: str) -> dict[str, Any]:
        output_id = str(output_id or "").strip() or "jack"
        async with self.config_lock:
            previous_output_id = self.config.audio_output_id
        if not output_id.startswith("upnp:"):
            await asyncio.to_thread(self.audio_service.set_output, output_id)
        async with self.config_lock:
            self.config.audio_output_id = output_id
            self.config.normalize()
            self.config_repository.save(self.config)
            config_copy = ControllerConfig(**self.config.to_public_dict())
        if previous_output_id.startswith("upnp:") and previous_output_id != output_id:
            try:
                await asyncio.to_thread(self.upnp_service.stop, previous_output_id)
            except Exception:
                pass
        return (await asyncio.to_thread(self._build_audio_state, config_copy, True)).to_public_dict()

    async def get_upnp_state(self) -> dict[str, Any]:
        async with self.config_lock:
            config_copy = ControllerConfig(**self.config.to_public_dict())
        return await asyncio.to_thread(self._build_upnp_status, config_copy)

    async def discover_upnp(self, seconds: int) -> dict[str, Any]:
        payload = await asyncio.to_thread(self.upnp_service.discover, seconds)
        async with self.config_lock:
            config_copy = ControllerConfig(**self.config.to_public_dict())
        selected_id = config_copy.audio_output_id if config_copy.audio_output_id.startswith("upnp:") else None
        payload["selected_output_id"] = selected_id
        return payload

    async def set_output_playback(self, playing: bool) -> dict[str, Any]:
        async with self.config_lock:
            config_copy = ControllerConfig(**self.config.to_public_dict())
        if not config_copy.audio_output_id.startswith("upnp:"):
            return await self.get_audio_state()

        async with self.state_lock:
            current_title = self.state.title
            current_artist = self.state.artist
            station = self.state.station
        source_stream_url = await asyncio.to_thread(self.audio_resolver.resolve, station)
        relay_stream_url = _build_upnp_stream_url(station.id)
        if playing:
            await asyncio.to_thread(
                self.upnp_service.play_stream,
                config_copy.audio_output_id,
                relay_stream_url,
                source_probe_url=source_stream_url,
                title=current_title or station.name,
                artist=current_artist or "",
                station_name=station.name,
            )
        else:
            await asyncio.to_thread(self.upnp_service.stop, config_copy.audio_output_id)
        return await self.get_audio_state()

    async def get_config(self) -> dict[str, Any]:
        async with self.config_lock:
            return self.config.to_public_dict()

    async def update_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with self.config_lock:
            self.config.update_from_payload(payload)
            self.config_repository.save(self.config)
        return await self.snapshot()

    async def list_backups(self) -> dict[str, Any]:
        return {"backups": self.config_repository.list_backups()}

    async def create_backup(self) -> dict[str, Any]:
        async with self.config_lock:
            path = self.config_repository.manual_backup(self.config)
        return {"ok": True, "backup": path.name}

    async def run_selftest(self) -> dict[str, Any]:
        async with self.state_lock:
            station_id = self.state.selected_station_id
        async with self.config_lock:
            config_copy = ControllerConfig(**self.config.to_public_dict())
        return await asyncio.to_thread(self.selftest_service.run, station_id, config_copy)

    async def get_update_status(self) -> dict[str, Any]:
        async with self.config_lock:
            configured_url = self.config.update_source_zip_url
        return await asyncio.to_thread(self.update_service.status, configured_url)

    async def apply_update(self) -> dict[str, Any]:
        return await asyncio.to_thread(self.update_service.apply_git_update)

    async def _get_selected_station_id(self) -> str:
        async with self.state_lock:
            return self.state.selected_station_id

    @staticmethod
    def _to_local_cover_url(url: str) -> str:
        if url.startswith("/"):
            return url
        return f"/cover-proxy?url={quote(url, safe='')}"

    def _ensure_configured_output_applied(self) -> None:
        if self.config.audio_output_id.startswith("upnp:"):
            return
        try:
            self.audio_service.set_output(self.config.audio_output_id)
        except Exception:
            return

    def _build_audio_state(self, config: ControllerConfig, force_upnp_refresh: bool = False) -> AudioState:
        local_state = self.audio_service.get_state()
        upnp_outputs: list[AudioOutput] = []
        selected_upnp_renderer = None
        upnp_error: str | None = None

        try:
            renderers = self.upnp_service.list_renderers(force_refresh=force_upnp_refresh, timeout_seconds=4 if force_upnp_refresh else 2)
        except Exception as exc:  # noqa: BLE001
            renderers = []
            upnp_error = str(exc)

        local_outputs = self._filter_local_outputs(local_state.outputs)
        for renderer in renderers:
            default = config.audio_output_id == renderer.id
            upnp_outputs.append(
                AudioOutput(
                    id=renderer.id,
                    label=renderer.friendly_name,
                    kind="upnp",
                    default=default,
                    raw_name=renderer.friendly_name,
                    backend_ref=renderer.id,
                )
            )
            if default:
                selected_upnp_renderer = renderer

        outputs = tuple(self._mark_local_defaults(local_outputs, config.audio_output_id) + upnp_outputs)

        if config.audio_output_id.startswith("upnp:"):
            message = upnp_error
            volume_percent = 0
            muted = False
            transport_playing = False
            selected_label = selected_upnp_renderer.friendly_name if selected_upnp_renderer else "WLAN-Lautsprecher"
            if selected_upnp_renderer is None and outputs:
                selected_label = next((item.label for item in outputs if item.id == config.audio_output_id), selected_label)
                if not message:
                    message = "Ausgewählter WLAN-Lautsprecher momentan nicht gefunden"
            elif selected_upnp_renderer is not None:
                try:
                    volume_percent = self.upnp_service.get_volume(selected_upnp_renderer.id) or 0
                    muted = bool(self.upnp_service.get_mute(selected_upnp_renderer.id) or False)
                    transport_state = (self.upnp_service.get_transport_state(selected_upnp_renderer.id) or "").strip().upper()
                    transport_playing = transport_state in {"PLAYING", "TRANSITIONING"}
                except Exception as exc:  # noqa: BLE001
                    if not message:
                        message = str(exc)
            return AudioState(
                available=selected_upnp_renderer is not None,
                backend="upnp",
                volume_percent=volume_percent,
                muted=muted,
                outputs=outputs,
                selected_output_id=config.audio_output_id,
                selected_output_label=selected_label,
                message=message,
                route_kind="upnp",
                supports_transport=selected_upnp_renderer is not None,
                transport_playing=transport_playing,
            )

        selected_local = next((item for item in outputs if item.default and item.kind != "upnp"), None)
        if selected_local is None:
            selected_local = next((item for item in outputs if item.kind != "upnp"), None)
        return AudioState(
            available=local_state.available,
            backend=local_state.backend,
            volume_percent=local_state.volume_percent,
            muted=local_state.muted,
            outputs=outputs,
            selected_output_id=selected_local.id if selected_local else local_state.selected_output_id,
            selected_output_label=selected_local.label if selected_local else local_state.selected_output_label,
            message=local_state.message,
            route_kind="local",
            supports_transport=False,
            transport_playing=False,
        )

    def _build_upnp_status(self, config: ControllerConfig) -> dict[str, Any]:
        payload = self.upnp_service.status()
        payload["selected_output_id"] = config.audio_output_id if config.audio_output_id.startswith("upnp:") else None
        payload["selected_output_label"] = None
        selected = payload.get("selected_output_id")
        for renderer in payload.get("renderers") or []:
            if renderer.get("id") == selected:
                payload["selected_output_label"] = renderer.get("friendly_name")
                break
        return payload

    @staticmethod
    def _filter_local_outputs(outputs: tuple[AudioOutput, ...]) -> list[AudioOutput]:
        preferred = [output for output in outputs if output.kind == "jack"]
        if preferred:
            return preferred
        fallback = [output for output in outputs if output.kind != "bluetooth"]
        return fallback if fallback else list(outputs)

    @staticmethod
    def _mark_local_defaults(outputs: list[AudioOutput], selected_output_id: str) -> list[AudioOutput]:
        if selected_output_id.startswith("upnp:"):
            return [
                AudioOutput(
                    id=output.id,
                    label=output.label,
                    kind=output.kind,
                    default=False,
                    raw_name=output.raw_name,
                    backend_ref=output.backend_ref,
                )
                for output in outputs
            ]

        if selected_output_id:
            marked = []
            any_selected = False
            for output in outputs:
                is_selected = output.id == selected_output_id
                any_selected = any_selected or is_selected
                marked.append(
                    AudioOutput(
                        id=output.id,
                        label=output.label,
                        kind=output.kind,
                        default=is_selected,
                        raw_name=output.raw_name,
                        backend_ref=output.backend_ref,
                    )
                )
            if any_selected:
                return marked
        return outputs

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self.refresh_selected_station()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Polling refresh failed: %s", exc)
            await asyncio.sleep(settings.poll_interval_seconds)


services = AppServices()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await services.start()
    try:
        yield
    finally:
        await services.stop()


app = FastAPI(title="ON Radio + 80s80s Cover Bridge", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def index() -> RedirectResponse:
    return RedirectResponse(url="/controller", status_code=302)


@app.get("/controller", response_class=HTMLResponse)
async def controller(request: Request) -> HTMLResponse:
    snapshot = await services.snapshot()
    context = {
        "request": request,
        "stations": [station.public_dict() for station in STATIONS],
        "initial_state_json": json.dumps(snapshot, ensure_ascii=False),
        "poll_interval_ms": settings.poll_interval_seconds * 1000,
        "display_url": snapshot.get("display_url") or _build_display_url(snapshot.get("controller_url") or _build_controller_url()),
    }
    return templates.TemplateResponse("controller.html", context)


@app.get("/display", response_class=HTMLResponse)
async def display(request: Request) -> HTMLResponse:
    snapshot = await services.snapshot()
    controller_url = snapshot.get("controller_url") or _build_controller_url()
    context = {
        "request": request,
        "initial_state_json": json.dumps(snapshot, ensure_ascii=False),
        "poll_interval_ms": settings.poll_interval_seconds * 1000,
        "power_button_enabled": settings.display_power_button_enabled and _is_loopback_request(request),
        "local_audio_button_enabled": settings.display_local_audio_button_enabled and _is_loopback_request(request),
        "controller_qr_enabled": settings.display_controller_qr_enabled,
        "controller_qr_available": QR_CODE_AVAILABLE,
        "controller_url": controller_url,
        "controller_host": _controller_host_label(controller_url),
    }
    return templates.TemplateResponse("display.html", context)


@app.get("/api/stations")
async def list_stations() -> dict[str, list[dict[str, str]]]:
    return {"stations": [station.public_dict() for station in STATIONS]}


@app.get("/api/state")
async def get_state() -> dict[str, Any]:
    return await services.snapshot()


@app.get("/api/audio/state")
async def get_audio_state() -> dict[str, Any]:
    return await services.get_audio_state()


@app.get("/api/upnp/state")
async def get_upnp_state() -> dict[str, Any]:
    return await services.get_upnp_state()


@app.get("/api/config")
async def get_config() -> dict[str, Any]:
    return await services.get_config()


@app.get("/api/backups")
async def get_backups() -> dict[str, Any]:
    return await services.list_backups()


@app.get("/api/update/status")
async def get_update_status() -> dict[str, Any]:
    return await services.get_update_status()


@app.post("/api/update/check")
async def check_update() -> dict[str, Any]:
    return await services.get_update_status()


@app.post("/api/update/apply")
async def apply_update() -> dict[str, Any]:
    try:
        return await services.apply_update()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/config")
async def post_config(payload: ConfigUpdatePayload) -> dict[str, Any]:
    try:
        return await services.update_config(payload.model_dump(exclude_none=True))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/backups/create")
async def create_backup() -> dict[str, Any]:
    return await services.create_backup()


@app.post("/api/audio/volume")
async def set_audio_volume(payload: AudioVolumePayload) -> dict[str, Any]:
    try:
        return await services.set_audio_volume(payload.percent)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/audio/volume-delta")
async def change_audio_volume(payload: AudioVolumeDeltaPayload) -> dict[str, Any]:
    try:
        return await services.change_audio_volume(payload.delta)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/audio/mute")
async def set_audio_muted(payload: MutePayload) -> dict[str, Any]:
    try:
        return await services.set_audio_muted(payload.muted)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/audio/mute-toggle")
async def toggle_audio_mute() -> dict[str, Any]:
    try:
        return await services.toggle_audio_mute()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/audio/output")
async def set_audio_output(payload: AudioOutputPayload) -> dict[str, Any]:
    try:
        return await services.set_audio_output(payload.output_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/output/playback")
async def set_output_playback(payload: OutputPlaybackPayload) -> dict[str, Any]:
    try:
        return await services.set_output_playback(payload.playing)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/upnp/discover")
async def discover_upnp(payload: UpnpDiscoveryPayload) -> dict[str, Any]:
    try:
        return await services.discover_upnp(payload.seconds)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/selftest")
async def run_selftest() -> dict[str, Any]:
    return await services.run_selftest()


@app.get("/controller-qr.svg")
async def controller_qr_svg() -> Response:
    if not settings.display_controller_qr_enabled:
        raise HTTPException(status_code=404, detail="QR-Code ist deaktiviert")
    if not QR_CODE_AVAILABLE:
        raise HTTPException(status_code=503, detail="QR-Code-Unterstuetzung nicht installiert")

    svg = _build_controller_qr_svg(_build_controller_url())
    headers = {
        "Cache-Control": "public, max-age=300",
    }
    return Response(content=svg, media_type="image/svg+xml", headers=headers)


@app.get("/cover-proxy")
async def cover_proxy(url: str = Query(..., min_length=8)) -> Response:
    payload = await services.get_cover_payload(url)
    if payload is None:
        raise HTTPException(status_code=404, detail="Cover konnte nicht geladen werden")
    headers = {
        "Cache-Control": "public, max-age=3600",
    }
    return Response(content=payload.content, media_type=payload.content_type, headers=headers)


@app.get("/stream/{station_id}")
async def station_stream(station_id: str) -> RedirectResponse:
    try:
        resolved_url = await services.resolve_station_stream(station_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unbekannter Sender") from exc
    return RedirectResponse(url=resolved_url, status_code=307)


@app.api_route("/upnp-stream/{station_id}", methods=["GET", "HEAD"])
async def upnp_station_stream(station_id: str, request: Request) -> Response:
    station = STATION_MAP.get(station_id)
    if station is None:
        raise HTTPException(status_code=404, detail="Unbekannter Sender")

    try:
        upstream_url = await services.resolve_station_stream(station_id)
        upstream = await asyncio.to_thread(
            requests.get,
            upstream_url,
            stream=True,
            allow_redirects=True,
            timeout=(5, settings.playlist_timeout_seconds),
            headers={"User-Agent": settings.user_agent},
        )
        upstream.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"UPnP-Relay konnte den Stream nicht öffnen: {exc}") from exc

    content_type = (upstream.headers.get("Content-Type") or "audio/mpeg").split(";", 1)[0].strip() or "audio/mpeg"
    headers = {
        "Cache-Control": "no-store",
        "X-Accel-Buffering": "no",
    }

    if request.method == "HEAD":
        upstream.close()
        return Response(status_code=200, media_type=content_type, headers=headers)

    def generate() -> Any:
        try:
            for chunk in upstream.iter_content(chunk_size=64 * 1024):
                if chunk:
                    yield chunk
        finally:
            upstream.close()

    return StreamingResponse(generate(), media_type=content_type, headers=headers)


@app.post("/api/select")
async def select_station(payload: StationSelection) -> dict[str, Any]:
    try:
        return await services.select_station(payload.station_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unbekannter Sender") from exc


@app.post("/api/stations/next")
async def select_next_station() -> dict[str, Any]:
    return await services.select_relative_station(1)


@app.post("/api/stations/prev")
async def select_prev_station() -> dict[str, Any]:
    return await services.select_relative_station(-1)


@app.post("/api/playback")
async def set_playback(payload: PlaybackState) -> dict[str, Any]:
    return await services.set_playback(payload.playing)


@app.post("/api/refresh")
async def refresh() -> dict[str, Any]:
    return await services.refresh_selected_station()


@app.post("/api/system/poweroff", status_code=202)
async def poweroff_system(request: Request) -> dict[str, str]:
    if not settings.display_power_button_enabled:
        raise HTTPException(status_code=404, detail="Herunterfahren ist deaktiviert")

    if settings.power_button_local_only and not _is_loopback_request(request):
        raise HTTPException(status_code=403, detail="Herunterfahren ist nur direkt auf dem Raspberry Pi erlaubt")

    try:
        _schedule_poweroff()
    except FileNotFoundError as exc:
        logger.exception("Poweroff command is unavailable")
        raise HTTPException(status_code=500, detail="Herunterfahren ist auf diesem System nicht verfuegbar") from exc

    client_host = request.client.host if request.client else "unknown"
    logger.warning("Poweroff requested from %s", client_host)
    return {
        "ok": True,
        "message": "Raspberry Pi faehrt herunter…",
    }



def _build_controller_qr_svg(controller_url: str) -> bytes:
    if not QR_CODE_AVAILABLE or qrcode is None or SvgPathImage is None or ERROR_CORRECT_M is None:
        raise HTTPException(status_code=503, detail="QR-Code-Unterstuetzung nicht installiert")

    qr = qrcode.QRCode(
        error_correction=ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )
    qr.add_data(controller_url)
    qr.make(fit=True)

    image = qr.make_image(image_factory=SvgPathImage)
    output = io.BytesIO()
    image.save(output)
    svg = output.getvalue()
    return svg if isinstance(svg, bytes) else str(svg).encode("utf-8")



def _build_controller_url() -> str:
    override = settings.controller_url_override.strip()
    if override:
        return override

    scheme = settings.controller_url_scheme.strip().lower() or "http"
    host = settings.controller_public_host.strip() or _detect_public_host()
    host_for_url = _format_host_for_url(host)

    default_port = 80 if scheme == "http" else 443 if scheme == "https" else None
    port_suffix = "" if default_port == settings.port else f":{settings.port}"
    return f"{scheme}://{host_for_url}{port_suffix}/controller"



def _build_display_url(controller_url: str | None = None) -> str:
    source = (controller_url or _build_controller_url()).rstrip('/')
    if source.endswith('/controller'):
        return source[:-11] + '/display'
    return source + '/display'



def _build_upnp_stream_url(station_id: str) -> str:
    host = settings.controller_public_host.strip() or _detect_public_host()
    host_for_url = _format_host_for_url(host)
    port_suffix = '' if settings.port == 80 else f':{settings.port}'
    return f'http://{host_for_url}{port_suffix}/upnp-stream/{quote(station_id, safe="")}'



def _controller_host_label(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc:
        return parsed.netloc
    return url



def _format_host_for_url(host: str) -> str:
    normalized = host.strip() or "127.0.0.1"
    if normalized.startswith("["):
        return normalized

    try:
        ip_address = ipaddress.ip_address(normalized)
    except ValueError:
        return normalized

    if isinstance(ip_address, ipaddress.IPv6Address):
        return f"[{normalized}]"
    return normalized



def _detect_public_host() -> str:
    udp_candidates = [
        (socket.AF_INET, ("10.255.255.255", 1)),
        (socket.AF_INET, ("8.8.8.8", 80)),
    ]

    for family, target in udp_candidates:
        try:
            with socket.socket(family, socket.SOCK_DGRAM) as sock:
                sock.connect(target)
                candidate = sock.getsockname()[0]
        except OSError:
            continue
        if _is_public_candidate(candidate):
            return candidate

    try:
        hostname = socket.gethostname()
        for entry in socket.getaddrinfo(hostname, None, family=socket.AF_INET, type=socket.SOCK_STREAM):
            candidate = entry[4][0]
            if _is_public_candidate(candidate):
                return candidate
    except OSError:
        pass

    return "127.0.0.1"



def _is_public_candidate(value: str) -> bool:
    try:
        return not ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False



def _is_loopback_request(request: Request) -> bool:
    client = request.client
    if client is None or not client.host:
        return False

    host = client.host.strip()
    if host == "localhost":
        return True

    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False



def _schedule_poweroff() -> None:
    command = _poweroff_command()
    delay_seconds = max(1, settings.poweroff_delay_seconds)
    command_text = " ".join(shlex.quote(part) for part in command)
    shell_command = f"sleep {delay_seconds}; exec {command_text}"

    subprocess.Popen(  # noqa: S603,S607
        ["/bin/sh", "-lc", shell_command],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
        env=os.environ.copy(),
    )



def _poweroff_command() -> list[str]:
    systemctl_path = shutil.which("systemctl") or "/usr/bin/systemctl"
    if os.geteuid() == 0:
        return [systemctl_path, "poweroff"]

    sudo_path = shutil.which("sudo") or "/usr/bin/sudo"
    return [sudo_path, "-n", systemctl_path, "poweroff"]
