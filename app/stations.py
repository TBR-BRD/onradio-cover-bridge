from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any
from urllib.parse import urlparse


ALLOWED_AUDIO_MODES = {"direct", "pls", "m3u"}
CUSTOM_STATION_ID_PREFIX = "custom-"


@dataclass(frozen=True, slots=True)
class Station:
    id: str
    name: str
    homepage_url: str
    audio_url: str
    metadata_url: str
    audio_mode: str = "direct"
    metadata_mode: str = "on_playlist_html"
    metadata_fallback_url: str | None = None
    metadata_fallback_mode: str | None = None
    metadata_station_label: str | None = None
    metadata_station_aliases: tuple[str, ...] = ()
    metadata_station_id: int | None = None
    is_custom: bool = False

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "stream_url": f"/stream/{self.id}",
            "homepage_url": self.homepage_url,
            "audio_url": self.audio_url,
            "audio_mode": self.audio_mode,
            "custom": self.is_custom,
            "removable": True,
        }


def _on_station(
    *,
    station_id: str,
    name: str,
    slug: str,
    homepage_url: str,
    playlist_url: str | None = None,
) -> Station:
    return Station(
        id=station_id,
        name=name,
        homepage_url=homepage_url,
        audio_url=f"https://{slug}.radionetz.de/{slug}.mp3",
        metadata_url=f"https://www.0nradio.com/now_playing/{slug}.json",
        metadata_mode="0nradio_json",
        metadata_fallback_url=playlist_url,
        metadata_fallback_mode="on_playlist_html" if playlist_url else None,
    )


STATIONS: tuple[Station, ...] = (
    _on_station(
        station_id="on-radio",
        name="ON Radio",
        slug="0n-radio",
        homepage_url="https://onradio.de/",
        playlist_url="https://onradio.de/playlist.html",
    ),
    _on_station(
        station_id="on-hits",
        name="ON Hits",
        slug="0n-hits",
        homepage_url="https://hits.onradio.de/",
        playlist_url="https://hits.onradio.de/playlist.html",
    ),
    _on_station(
        station_id="on-charts",
        name="ON Charts",
        slug="0n-charts",
        homepage_url="https://charts.onradio.de/",
        playlist_url="https://charts.onradio.de/playlist.html",
    ),
    _on_station(
        station_id="on-oldies",
        name="ON Oldies",
        slug="0n-oldies",
        homepage_url="https://oldies.onradio.de/",
        playlist_url="https://oldies.onradio.de/playlist.html",
    ),
    _on_station(
        station_id="on-schlager",
        name="ON Schlager",
        slug="0n-schlager",
        homepage_url="https://schlager.onradio.de/",
        playlist_url="https://schlager.onradio.de/playlist.html",
    ),
    _on_station(
        station_id="on-chillout",
        name="ON Chillout",
        slug="0n-chillout",
        homepage_url="https://chillout.onradio.de/",
        playlist_url="https://chillout.onradio.de/playlist.html",
    ),
    _on_station(
        station_id="on-jukebox",
        name="ON Jukebox",
        slug="0n-jukebox",
        homepage_url="https://www.0nradio.com/",
    ),
    _on_station(
        station_id="on-relax",
        name="ON Relax",
        slug="0n-relax",
        homepage_url="https://www.0nradio.com/",
    ),
    _on_station(
        station_id="on-party",
        name="ON Party",
        slug="0n-party",
        homepage_url="https://www.0nradio.com/",
    ),
    _on_station(
        station_id="on-greatest-hits",
        name="ON Greatest Hits",
        slug="0n-greatesthits",
        homepage_url="https://www.0nradio.com/",
    ),
    _on_station(
        station_id="on-pop",
        name="ON Pop",
        slug="0n-pop",
        homepage_url="https://www.0nradio.com/",
    ),
    _on_station(
        station_id="on-gold",
        name="ON Gold",
        slug="0n-gold",
        homepage_url="https://www.0nradio.com/",
    ),
    _on_station(
        station_id="on-dance",
        name="ON Dance",
        slug="0n-dance",
        homepage_url="https://www.0nradio.com/",
    ),
    _on_station(
        station_id="on-lounge",
        name="ON Lounge",
        slug="0n-lounge",
        homepage_url="https://www.0nradio.com/",
    ),
    _on_station(
        station_id="on-love",
        name="ON Love",
        slug="0n-love",
        homepage_url="https://www.0nradio.com/",
    ),
    _on_station(
        station_id="on-disco",
        name="ON Disco",
        slug="0n-disco",
        homepage_url="https://www.0nradio.com/",
    ),
    _on_station(
        station_id="on-techno",
        name="ON Techno",
        slug="0n-techno",
        homepage_url="https://www.0nradio.com/",
    ),
    _on_station(
        station_id="on-christmas",
        name="ON Christmas",
        slug="0n-christmas",
        homepage_url="https://www.0nradio.com/",
    ),
    Station(
        id="80s80s-radio",
        name="80s80s",
        homepage_url="https://www.80s80s.de/streams/80s80s",
        audio_url="https://streams.80s80s.de/web/mp3-128/streams.80s80s.de/play.pls",
        metadata_url="https://www.80s80s.de/streams/api",
        audio_mode="pls",
        metadata_mode="80s80s_api",
        metadata_fallback_url="https://www.80s80s.de/streams/80s80s",
        metadata_fallback_mode="80s80s_page_html",
        metadata_station_label="80s80s DIGITAL",
        metadata_station_aliases=("80s80s Radio", "80s80s Digital Web"),
        metadata_station_id=62,
    ),
    Station(
        id="80s80s-in-the-mix",
        name="80s80s In The Mix",
        homepage_url="https://www.80s80s.de/80s80s-in-the-mix",
        audio_url="https://streams.80s80s.de/mix/mp3-128/streams.80s80s.de/play.pls",
        metadata_url="https://www.80s80s.de/streams/api",
        audio_mode="pls",
        metadata_mode="80s80s_api",
        metadata_fallback_url="https://www.80s80s.de/80s80s-in-the-mix",
        metadata_fallback_mode="80s80s_page_html",
        metadata_station_label="80s80s In The Mix",
        metadata_station_aliases=("IN THE MIX",),
    ),
    Station(
        id="80s80s-italo-disco",
        name="80s80s Italo Disco",
        homepage_url="https://www.80s80s.de/streams/80s80s-italo-disco",
        audio_url="https://streams.80s80s.de/italohits/mp3-128/streams.80s80s.de/play.pls",
        metadata_url="https://www.80s80s.de/streams/api",
        audio_mode="pls",
        metadata_mode="80s80s_api",
        metadata_fallback_url="https://www.80s80s.de/streams/80s80s-italo-disco",
        metadata_fallback_mode="80s80s_page_html",
        metadata_station_label="80s80s Italo Hits",
        metadata_station_aliases=("80s80s Italo Disco", "ITALO DISCO", "Italo Hits"),
    ),
    Station(
        id="80s80s-italo-disco-in-the-mix",
        name="80s80s Italo Disco In The Mix",
        homepage_url="https://www.80s80s.de/radios/italo-disco-in-the-mix",
        audio_url="https://streams.80s80s.de/italodiscomix/mp3-128/streams.80s80s.de/play.pls",
        metadata_url="https://www.80s80s.de/streams/api",
        audio_mode="pls",
        metadata_mode="80s80s_api",
        metadata_fallback_url="https://www.80s80s.de/radios/italo-disco-in-the-mix",
        metadata_fallback_mode="80s80s_page_html",
        metadata_station_label="80s80s Italo Disco In The Mix",
        metadata_station_aliases=("ITALO DISCO IN THE MIX", "Italo Disco In The Mix", "80s80s-italo Mix 12"),
    ),
    Station(
        id="80s80s-maxis",
        name="80s80s Maxis",
        homepage_url="https://www.80s80s.de/80s80s-maxis",
        audio_url="https://streams.80s80s.de/maxis/mp3-128/streams.80s80s.de/play.pls",
        metadata_url="https://www.80s80s.de/streams/api",
        audio_mode="pls",
        metadata_mode="80s80s_api",
        metadata_fallback_url="https://www.80s80s.de/80s80s-maxis",
        metadata_fallback_mode="80s80s_page_html",
        metadata_station_label="80s80s Maxis",
        metadata_station_aliases=("MAXIS",),
    ),
    Station(
        id="80s80s-party",
        name="80s80s Party",
        homepage_url="https://www.80s80s.de/streams/80s80s-party",
        audio_url="https://streams.80s80s.de/party/mp3-128/streams.80s80s.de/play.pls",
        metadata_url="https://www.80s80s.de/streams/api",
        audio_mode="pls",
        metadata_mode="80s80s_api",
        metadata_fallback_url="https://www.80s80s.de/streams/80s80s-party",
        metadata_fallback_mode="80s80s_page_html",
        metadata_station_label="80s80s Partyhits",
        metadata_station_aliases=("80s80s Party", "PARTY"),
    ),
    Station(
        id="80s80s-summer",
        name="80s80s Summer",
        homepage_url="https://www.80s80s.de/80s80s-summer",
        audio_url="https://streams.80s80s.de/summerhits/mp3-128/streams.80s80s.de/play.pls",
        metadata_url="https://www.80s80s.de/streams/api",
        audio_mode="pls",
        metadata_mode="80s80s_api",
        metadata_fallback_url="https://www.80s80s.de/80s80s-summer",
        metadata_fallback_mode="80s80s_page_html",
        metadata_station_label="80s80s Summerhits",
        metadata_station_aliases=("80s80s Summer", "SUMMER"),
    ),
    Station(
        id="80s80s-dance",
        name="80s80s Dance",
        homepage_url="https://www.80s80s.de/80s80s-dance",
        audio_url="https://streams.80s80s.de/dance/mp3-128/streams.80s80s.de/play.pls",
        metadata_url="https://www.80s80s.de/streams/api",
        audio_mode="pls",
        metadata_mode="80s80s_api",
        metadata_fallback_url="https://www.80s80s.de/80s80s-dance",
        metadata_fallback_mode="80s80s_page_html",
        metadata_station_label="80s80s Dance",
        metadata_station_aliases=("DANCE",),
    ),
    Station(
        id="80s80s-techno",
        name="80s80s Techno",
        homepage_url="https://www.80s80s.de/techno",
        audio_url="https://streams.80s80s.de/techno/mp3-128/streams.80s80s.de/play.pls",
        metadata_url="https://www.80s80s.de/streams/api",
        audio_mode="pls",
        metadata_mode="80s80s_api",
        metadata_fallback_url="https://www.80s80s.de/techno",
        metadata_fallback_mode="80s80s_page_html",
        metadata_station_label="80s80s Techno",
        metadata_station_aliases=("TECHNO",),
    ),
    Station(
        id="80s80s-christmas",
        name="80s80s Christmas",
        homepage_url="https://www.80s80s.de/streams/80s80s-xmas",
        audio_url="https://streams.80s80s.de/christmas/mp3-128/streams.80s80s.de/play.pls",
        metadata_url="https://www.80s80s.de/streams/api",
        audio_mode="pls",
        metadata_mode="80s80s_api",
        metadata_fallback_url="https://www.80s80s.de/streams/80s80s-xmas",
        metadata_fallback_mode="80s80s_page_html",
        metadata_station_label="80s80s Christmas",
        metadata_station_aliases=("80s XMAS", "80s80s XMAS", "XMAS"),
    ),
    Station(
        id="sunshine-live",
        name="Sunshine Live",
        homepage_url="https://www.sunshine-live.de/",
        audio_url="https://stream.sunshine-live.de/live/mp3-128/stream.sunshine-live.de/",
        metadata_url="https://stream.sunshine-live.de/live/mp3-128/stream.sunshine-live.de/",
        metadata_mode="icy_stream",
    ),
    Station(
        id="sunshine-live-80s",
        name="Sunshine Live 80s",
        homepage_url="https://www.sunshine-live.de/80s-channel",
        audio_url="https://stream.sunshine-live.de/80er/mp3-128/stream.sunshine-live.de/",
        metadata_url="https://stream.sunshine-live.de/80er/mp3-128/stream.sunshine-live.de/",
        metadata_mode="icy_stream",
    ),
    Station(
        id="radio-fritz",
        name="Radio Fritz",
        homepage_url="https://www.fritz.de/",
        audio_url="https://www.fritz.de/live.m3u",
        metadata_url="https://www.fritz.de/live.m3u",
        audio_mode="m3u",
        metadata_mode="icy_stream",
    ),
    Station(
        id="rbb888",
        name="rbb 88.8",
        homepage_url="https://www.rbb888.de/",
        audio_url="https://www.rbb888.de/live.m3u",
        metadata_url="https://www.rbb888.de/live.m3u",
        audio_mode="m3u",
        metadata_mode="icy_stream",
    ),
    Station(
        id="radio-1046-rtl",
        name="104.6 RTL",
        homepage_url="https://www.104.6rtl.com/channel/live",
        audio_url="https://stream.104.6rtl.com/rtl-live/mp3-128",
        metadata_url="https://stream.104.6rtl.com/rtl-live/mp3-128",
        metadata_mode="icy_stream",
    ),
    Station(
        id="radio-rs2",
        name="94,3 RS2",
        homepage_url="https://www.rs2.de/musik/streams/94-3-rs2-livestream",
        audio_url="http://stream.rs2.de/rs2/mp3-128",
        metadata_url="http://stream.rs2.de/rs2/mp3-128",
        metadata_mode="icy_stream",
    ),
    Station(
        id="antenne-bayern-workout-mix",
        name="Antenne Bayern Workout Mix",
        homepage_url="https://www.antenne.de/webradio/workout-hits",
        audio_url="https://stream.antenne.de/workout-hits/stream/aacp?aw_0_1st.playerid=airablenow.com",
        metadata_url="https://stream.antenne.de/workout-hits/stream/aacp?aw_0_1st.playerid=airablenow.com",
        metadata_mode="icy_stream",
    ),
    Station(
        id="absolut-relax",
        name="Absolut Relax",
        homepage_url="https://absolutradio.de/sender/relax",
        audio_url="https://absolut-relax.live-sm.absolutradio.de/absolut-relax/stream/aacp",
        metadata_url="https://absolut-relax.live-sm.absolutradio.de/absolut-relax/stream/aacp",
        metadata_mode="icy_stream",
    ),
    Station(
        id="absolut-bella",
        name="Absolut Bella",
        homepage_url="https://absolutradio.de/sender/bella",
        audio_url="https://absolut-bella.live-sm.absolutradio.de/absolut-bella/stream/aacp",
        metadata_url="https://absolut-bella.live-sm.absolutradio.de/absolut-bella/stream/aacp",
        metadata_mode="icy_stream",
    ),
    Station(
        id="rtl-radio",
        name="RTL Radio",
        homepage_url="https://www.rtlradio.de/",
        audio_url="http://stream.rtlradio.de/rtl-de-ukw/mp3-192",
        metadata_url="http://stream.rtlradio.de/rtl-de-ukw/mp3-192",
        metadata_mode="icy_stream",
    ),
    Station(
        id="megaradiomix-berlin",
        name="Megaradiomix Berlin",
        homepage_url="https://megaradiomix.de/",
        audio_url="https://stream.megaradiomix.de/megaradiomix-berlin.mp3",
        metadata_url="https://stream.megaradiomix.de/megaradiomix-berlin.mp3",
        metadata_mode="icy_stream",
    ),
    Station(
        id="antenne-brandenburg",
        name="Antenne Brandenburg (Potsdam)",
        homepage_url="https://www.rbb-online.de/antennebrandenburg/",
        audio_url="http://dispatcher.rndfnk.com/rbb/antennebrandenburg/live/mp3/mid",
        metadata_url="http://dispatcher.rndfnk.com/rbb/antennebrandenburg/live/mp3/mid",
        metadata_mode="icy_stream",
    ),
    Station(
        id="rbb24-inforadio",
        name="rbb24 Inforadio",
        homepage_url="https://www.inforadio.de/",
        audio_url="http://dispatcher.rndfnk.com/rbb/inforadio/live/mp3/mid",
        metadata_url="http://dispatcher.rndfnk.com/rbb/inforadio/live/mp3/mid",
        metadata_mode="icy_stream",
    ),
)

STATION_MAP: dict[str, Station] = {station.id: station for station in STATIONS}
DEFAULT_STATION_ID = STATIONS[0].id


def station_catalog(config: Any | None = None) -> tuple[Station, ...]:
    hidden_station_ids = _normalized_hidden_station_ids(getattr(config, "hidden_station_ids", ()))
    catalog = [station for station in STATIONS if station.id not in hidden_station_ids]
    existing_ids = {station.id for station in STATIONS}
    for payload in getattr(config, "custom_stations", ()) or ():
        station = station_from_payload(payload, existing_ids=existing_ids)
        if station is None:
            continue
        catalog.append(station)
        existing_ids.add(station.id)
    return tuple(catalog) or (STATIONS[0],)


def station_map(config: Any | None = None) -> dict[str, Station]:
    return {station.id: station for station in station_catalog(config)}


def first_station_id(config: Any | None = None) -> str:
    return station_catalog(config)[0].id


def normalize_custom_station_payload(payload: dict[str, Any], existing_ids: set[str] | None = None) -> dict[str, Any]:
    existing_ids = set(existing_ids or set())
    name = _clean_text(payload.get("name"), max_length=80)
    audio_url = _clean_url(payload.get("audio_url"))
    homepage_url = _clean_url(payload.get("homepage_url"), allow_empty=True)
    audio_mode = _clean_audio_mode(payload.get("audio_mode"))
    if not name:
        raise ValueError("Sendername fehlt")
    if not audio_url:
        raise ValueError("Stream-URL fehlt oder ist ungueltig")

    station_id = _clean_station_id(payload.get("id"))
    if not station_id or station_id in STATION_MAP or station_id in existing_ids:
        station_id = _unique_station_id(name, existing_ids | set(STATION_MAP))

    return {
        "id": station_id,
        "name": name,
        "homepage_url": homepage_url,
        "audio_url": audio_url,
        "audio_mode": audio_mode,
    }


def station_from_payload(payload: Any, existing_ids: set[str] | None = None) -> Station | None:
    if not isinstance(payload, dict):
        return None
    try:
        normalized = normalize_custom_station_payload(payload, existing_ids=existing_ids)
    except ValueError:
        return None
    return Station(
        id=normalized["id"],
        name=normalized["name"],
        homepage_url=normalized["homepage_url"],
        audio_url=normalized["audio_url"],
        metadata_url=normalized["audio_url"],
        audio_mode=normalized["audio_mode"],
        metadata_mode="icy_stream",
        is_custom=True,
    )


def _normalized_hidden_station_ids(values: Any) -> set[str]:
    if not isinstance(values, (list, tuple, set)):
        return set()
    return {str(value).strip() for value in values if str(value).strip() in STATION_MAP}


def _clean_text(value: Any, *, max_length: int) -> str:
    return " ".join(str(value or "").split())[:max_length]


def _clean_url(value: Any, *, allow_empty: bool = False) -> str:
    url = str(value or "").strip()
    if not url and allow_empty:
        return ""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return url


def _clean_audio_mode(value: Any) -> str:
    mode = str(value or "direct").strip().casefold()
    return mode if mode in ALLOWED_AUDIO_MODES else "direct"


def _clean_station_id(value: Any) -> str:
    station_id = str(value or "").strip().casefold()
    if not station_id.startswith(CUSTOM_STATION_ID_PREFIX):
        return ""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,78}[a-z0-9]", station_id):
        return ""
    return station_id


def _unique_station_id(name: str, existing_ids: set[str]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
    slug = slug or "radio"
    candidate = f"{CUSTOM_STATION_ID_PREFIX}{slug}"[:80].strip("-")
    if candidate not in existing_ids:
        return candidate
    suffix = 2
    while True:
        trimmed = candidate[: max(1, 80 - len(str(suffix)) - 1)].strip("-")
        next_candidate = f"{trimmed}-{suffix}"
        if next_candidate not in existing_ids:
            return next_candidate
        suffix += 1
