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


def _sunshine_station(*, station_id: str, name: str, slug: str) -> Station:
    audio_url = f"https://stream.sunshine-live.de/{slug}/mp3-192/homepage/"
    return Station(
        id=station_id,
        name=name,
        homepage_url="https://www.sunshine-live.de/music/channels",
        audio_url=audio_url,
        metadata_url=audio_url,
        metadata_mode="icy_stream",
    )


def _eighties_station(
    *,
    station_id: str,
    name: str,
    slug: str,
    metadata_station_id: int,
    metadata_station_label: str | None = None,
    metadata_station_aliases: tuple[str, ...] = (),
) -> Station:
    audio_url = f"https://streams.80s80s.de/{slug}/mp3-192/homepage/"
    homepage_slug = station_id.removeprefix("80s80s-")
    return Station(
        id=station_id,
        name=name,
        homepage_url=f"https://www.80s80s.de/streams/{homepage_slug}",
        audio_url=audio_url,
        metadata_url="https://www.80s80s.de/streams/api",
        metadata_mode="80s80s_api",
        metadata_fallback_url=f"https://www.80s80s.de/streams/{homepage_slug}",
        metadata_fallback_mode="80s80s_page_html",
        metadata_station_label=metadata_station_label or name,
        metadata_station_aliases=metadata_station_aliases,
        metadata_station_id=metadata_station_id,
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
    _eighties_station(
        station_id="80s80s-radio",
        name="80s80s",
        slug="web",
        metadata_station_id=62,
        metadata_station_label="80s80s DIGITAL",
        metadata_station_aliases=("80s80s Radio", "80s80s Digital Web"),
    ),
    _eighties_station(station_id="80s80s-alternative", name="80s80s Alternative", slug="alternative", metadata_station_id=788),
    _eighties_station(station_id="80s80s-bowie", name="80s80s Bowie", slug="davidbowie", metadata_station_id=84),
    _eighties_station(station_id="80s80s-breakdance", name="80s80s Breakdance", slug="breakdance", metadata_station_id=659),
    _eighties_station(station_id="80s80s-dance", name="80s80s Dance", slug="dance", metadata_station_id=673),
    _eighties_station(station_id="80s80s-dark-wave", name="80s80s Dark Wave", slug="darkwave", metadata_station_id=672),
    _eighties_station(
        station_id="80s80s-depeche-mode",
        name="80s80s Depeche Mode",
        slug="dm",
        metadata_station_id=87,
        metadata_station_label="D.M.",
        metadata_station_aliases=("80s80s Depeche Mode", "DEPECHE MODE"),
    ),
    _eighties_station(station_id="80s80s-deutsch", name="80s80s Deutsch", slug="deutsch", metadata_station_id=618),
    _eighties_station(station_id="80s80s-dinnerparty", name="80s80s Dinnerparty", slug="dinnerparty", metadata_station_id=660),
    _eighties_station(station_id="80s80s-ebm", name="80s80s EBM", slug="ebm", metadata_station_id=718),
    _eighties_station(station_id="80s80s-freestyle", name="80s80s Freestyle", slug="freestyle", metadata_station_id=800),
    _eighties_station(station_id="80s80s-funk-and-soul", name="80s80s Funk & Soul", slug="soul", metadata_station_id=517),
    _eighties_station(station_id="80s80s-hiphop", name="80s80s HipHop", slug="hiphop", metadata_station_id=647),
    _eighties_station(station_id="80s80s-in-the-mix", name="80s80s In The Mix", slug="mix", metadata_station_id=558),
    _eighties_station(station_id="80s80s-italo-disco", name="80s80s Italo Disco", slug="italohits", metadata_station_id=283),
    _eighties_station(
        station_id="80s80s-italo-disco-in-the-mix",
        name="80s80s Italo Disco In The Mix",
        slug="italodiscomix",
        metadata_station_id=834,
    ),
    _eighties_station(station_id="80s80s-jackson", name="80s80s Jackson", slug="mj", metadata_station_id=156),
    _eighties_station(station_id="80s80s-live", name="80s80s Live", slug="livemusic", metadata_station_id=635),
    _eighties_station(station_id="80s80s-love", name="80s80s Love", slug="love", metadata_station_id=85),
    _eighties_station(station_id="80s80s-maxis", name="80s80s Maxis", slug="maxis", metadata_station_id=596),
    _eighties_station(station_id="80s80s-ndw", name="80s80s NDW", slug="ndw", metadata_station_id=137),
    _eighties_station(station_id="80s80s-neo", name="80s80s Neo", slug="neo", metadata_station_id=616),
    _eighties_station(station_id="80s80s-party", name="80s80s Party", slug="party", metadata_station_id=252),
    _eighties_station(station_id="80s80s-pop-stories", name="80s80s Pop Stories", slug="popstories", metadata_station_id=772),
    _eighties_station(station_id="80s80s-prince", name="80s80s Prince", slug="100", metadata_station_id=111),
    _eighties_station(station_id="80s80s-queen", name="80s80s Queen", slug="queen", metadata_station_id=617),
    _eighties_station(station_id="80s80s-reggae", name="80s80s Reggae", slug="reggae", metadata_station_id=777),
    _eighties_station(station_id="80s80s-rock", name="80s80s Rock", slug="rock", metadata_station_id=440),
    _eighties_station(station_id="80s80s-romantic-rock", name="80s80s Romantic Rock", slug="romanticrock", metadata_station_id=792),
    _eighties_station(station_id="80s80s-soul-ballads", name="80s80s Soul Ballads", slug="soulballads", metadata_station_id=840),
    _eighties_station(station_id="80s80s-summer", name="80s80s Summer", slug="summerhits", metadata_station_id=569),
    _eighties_station(station_id="80s80s-techno", name="80s80s Techno", slug="techno", metadata_station_id=780),
    _eighties_station(station_id="80s80s-wave", name="80s80s Wave", slug="wave", metadata_station_id=284),
    _eighties_station(station_id="80s80s-wgt", name="80s80s WGT", slug="wgt", metadata_station_id=773),
    _eighties_station(
        station_id="80s80s-xmas",
        name="80s80s XMAS",
        slug="christmas",
        metadata_station_id=75,
        metadata_station_aliases=("80s80s Christmas", "80s XMAS", "XMAS"),
    ),
    _eighties_station(station_id="80s80s-yacht-rock", name="80s80s Yacht Rock", slug="yachtrock", metadata_station_id=846),
    _eighties_station(station_id="80s80s-baden-wuerttemberg", name="80s80s Baden-Wuerttemberg", slug="bawue", metadata_station_id=785),
    _eighties_station(station_id="80s80s-bayern", name="80s80s Bayern", slug="bayern", metadata_station_id=784),
    _eighties_station(station_id="80s80s-hessen", name="80s80s Hessen", slug="hessen", metadata_station_id=828),
    _eighties_station(
        station_id="80s80s-mecklenburg-vorpommern",
        name="80s80s Mecklenburg-Vorpommern",
        slug="80s80sMV",
        metadata_station_id=568,
    ),
    _eighties_station(station_id="80s80s-niedersachsen", name="80s80s Niedersachsen", slug="nds", metadata_station_id=782),
    _eighties_station(station_id="80s80s-nordrhein-westfalen", name="80s80s Nordrhein-Westfalen", slug="nrw", metadata_station_id=721),
    _sunshine_station(station_id="sunshine-live", name="Sunshine Live", slug="live"),
    _sunshine_station(station_id="sunshine-live-ch", name="Sunshine Live CH", slug="schweiz"),
    _sunshine_station(station_id="sunshine-live-schranz", name="Sunshine Live Schranz", slug="schranz"),
    _sunshine_station(station_id="sunshine-live-bounce", name="Sunshine Live Bounce", slug="bounce"),
    _sunshine_station(station_id="sunshine-live-touchdown-mix", name="Sunshine Live Touchdown Mix", slug="gladiators"),
    _sunshine_station(station_id="sunshine-live-electrique-cafe", name="Sunshine Live Electrique Cafe", slug="electriquecafe"),
    _sunshine_station(station_id="sunshine-live-2010s", name="Sunshine Live 2010s", slug="2010er"),
    _sunshine_station(station_id="sunshine-live-afro-house", name="Sunshine Live Afro House", slug="afrohouse"),
    _sunshine_station(station_id="sunshine-live-eurodance", name="Sunshine Live Eurodance", slug="eurodance"),
    _sunshine_station(station_id="sunshine-live-calm-flow", name="Sunshine Live Calm Flow", slug="calmflow"),
    _sunshine_station(station_id="sunshine-live-blue", name="Sunshine Live Blue", slug="Blue"),
    _sunshine_station(station_id="sunshine-live-hardcore", name="Sunshine Live Hardcore", slug="Hardcore"),
    _sunshine_station(station_id="sunshine-live-hardtechno", name="Sunshine Live Hardtechno", slug="Hardtechno"),
    _sunshine_station(station_id="sunshine-live-90s", name="Sunshine Live 90s", slug="90er"),
    _sunshine_station(station_id="sunshine-live-80s", name="Sunshine Live 80s", slug="80er"),
    _sunshine_station(station_id="sunshine-live-2000s", name="Sunshine Live 2000s", slug="2000er"),
    _sunshine_station(station_id="sunshine-live-house", name="Sunshine Live House", slug="house"),
    _sunshine_station(station_id="sunshine-live-melodic-beats", name="Sunshine Live Melodic Beats", slug="MelodicB"),
    _sunshine_station(station_id="sunshine-live-mix-mission", name="Sunshine Live Mix Mission", slug="mixmission"),
    _sunshine_station(station_id="sunshine-live-edm", name="Sunshine Live EDM", slug="edm"),
    _sunshine_station(station_id="sunshine-live-women-of-techno", name="Sunshine Live Women of Techno", slug="technoqueens"),
    _sunshine_station(station_id="sunshine-live-chillout", name="Sunshine Live Chillout", slug="sp8"),
    _sunshine_station(station_id="sunshine-live-ibiza", name="Sunshine Live Ibiza", slug="ibiza"),
    _sunshine_station(station_id="sunshine-live-classics", name="Sunshine Live Classics", slug="classics"),
    _sunshine_station(station_id="sunshine-live-trance", name="Sunshine Live Trance", slug="trance"),
    _sunshine_station(station_id="sunshine-live-techno", name="Sunshine Live Techno", slug="techno"),
    _sunshine_station(station_id="sunshine-live-workout", name="Sunshine Live Workout", slug="workout"),
    _sunshine_station(station_id="sunshine-live-lounge", name="Sunshine Live Lounge", slug="lounge"),
    _sunshine_station(station_id="sunshine-live-festival", name="Sunshine Live Festival", slug="festival"),
    _sunshine_station(station_id="sunshine-live-drum-and-bass", name="Sunshine Live Drum & Bass", slug="dnb"),
    _sunshine_station(station_id="sunshine-live-hardstyle", name="Sunshine Live Hardstyle", slug="hardstyle"),
    _sunshine_station(station_id="sunshine-live-nature-one", name="Sunshine Live Nature One", slug="natureone"),
    _sunshine_station(station_id="sunshine-live-mayday", name="Sunshine Live Mayday", slug="mayday"),
    _sunshine_station(station_id="sunshine-live-time-warp", name="Sunshine Live Time Warp", slug="timewarp"),
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
