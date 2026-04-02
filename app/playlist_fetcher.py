from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .audio_resolver import AudioStreamResolver
from .settings import settings
from .stations import Station

TIME_RE = re.compile(r"^\d{1,2}:\d{2}(?:\s*Uhr)?$", re.IGNORECASE)
SEPARATOR_RE = re.compile(r"\s+")
ICY_TITLE_RE = re.compile(r"StreamTitle='([^']*)';", re.IGNORECASE)
ICY_TITLE_RE_DOUBLE = re.compile(r'StreamTitle="([^"]*)";', re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class NowPlaying:
    played_at: str | None
    artist: str
    title: str
    source_url: str
    provider_cover_candidates: tuple[str, ...] = field(default_factory=tuple)


class PlaylistFetcher:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": settings.user_agent})
        self.audio_resolver = AudioStreamResolver()

    def fetch(self, station: Station) -> NowPlaying:
        errors: list[str] = []

        try:
            return self._fetch_by_mode(station.metadata_mode, station.metadata_url, station)
        except Exception as exc:  # noqa: BLE001 - fallback decides what to do next
            errors.append(f"{station.metadata_mode}: {_format_error(exc)}")

        if station.metadata_fallback_mode and station.metadata_fallback_url:
            try:
                return self._fetch_by_mode(
                    station.metadata_fallback_mode,
                    station.metadata_fallback_url,
                    station,
                )
            except Exception as exc:  # noqa: BLE001 - surface both failures in kiosk UI
                errors.append(f"{station.metadata_fallback_mode}: {_format_error(exc)}")

        raise ValueError("Metadatenabruf fehlgeschlagen: " + " | ".join(errors))

    def _fetch_by_mode(self, mode: str, url: str, station: Station) -> NowPlaying:
        if mode == "on_playlist_html":
            return self._fetch_on_html(url)
        if mode == "0nradio_json":
            return self._fetch_0nradio_json(url)
        if mode == "80s80s_api":
            return self._fetch_80s80s_api(station, url)
        if mode == "80s80s_page_html":
            return self._fetch_80s80s_page_html(station, url)
        if mode == "icy_stream":
            return self._fetch_icy_stream(station)
        raise ValueError(f"Unbekannter Metadaten-Modus: {mode}")

    def _fetch_on_html(self, url: str) -> NowPlaying:
        response = self.session.get(
            url,
            timeout=(5, settings.playlist_timeout_seconds),
        )
        response.raise_for_status()
        parsed = self.parse_on_playlist_html(response.text, base_url=url)
        return NowPlaying(
            played_at=parsed.played_at,
            artist=parsed.artist,
            title=parsed.title,
            source_url=url,
            provider_cover_candidates=parsed.provider_cover_candidates,
        )

    def _fetch_0nradio_json(self, url: str) -> NowPlaying:
        response = self.session.get(
            url,
            timeout=(5, settings.playlist_timeout_seconds),
        )
        response.raise_for_status()
        payload = response.json()
        parsed = self.parse_0nradio_json(payload, base_url=url)
        return NowPlaying(
            played_at=parsed.played_at,
            artist=parsed.artist,
            title=parsed.title,
            source_url=url,
            provider_cover_candidates=parsed.provider_cover_candidates,
        )

    def _fetch_80s80s_api(self, station: Station, url: str) -> NowPlaying:
        response = self.session.get(
            url,
            timeout=(5, settings.playlist_timeout_seconds),
        )
        response.raise_for_status()
        payload = response.json()
        match = _find_80s80s_station_entry(
            payload,
            expected_station_labels=_expected_station_labels(station),
            expected_station_id=station.metadata_station_id,
        )
        if match is None:
            raise ValueError("In der 80s80s API wurde kein passender Sender-Eintrag gefunden.")

        artist = _extract_first_text(match, "artist_name", "artist", "artistName")
        title = _extract_first_text(match, "song_title", "title", "songTitle")
        played_at = _normalize_played_at(
            _extract_first_text(
                match,
                "played_at",
                "playedAt",
                "start_time",
                "startTime",
                "time",
            )
        )
        if not _looks_like_track(artist, title):
            raise ValueError("Die 80s80s API hat keinen gueltigen aktuellen Titel geliefert.")

        return NowPlaying(
            played_at=played_at,
            artist=artist,
            title=title,
            source_url=url,
            provider_cover_candidates=_extract_cover_candidates_from_api_node(
                match,
                base_url=url,
            ),
        )

    def _fetch_80s80s_page_html(self, station: Station, url: str) -> NowPlaying:
        response = self.session.get(
            url,
            timeout=(5, settings.playlist_timeout_seconds),
        )
        response.raise_for_status()
        parsed = self.parse_80s80s_stream_page_html(
            response.text,
            expected_station_labels=_expected_station_labels(station),
            base_url=url,
        )
        return NowPlaying(
            played_at=parsed.played_at,
            artist=parsed.artist,
            title=parsed.title,
            source_url=url,
            provider_cover_candidates=parsed.provider_cover_candidates,
        )

    def _fetch_icy_stream(self, station: Station) -> NowPlaying:
        resolved_url = self.audio_resolver.resolve(station)
        response = None
        try:
            response = self.session.get(
                resolved_url,
                headers={"Icy-MetaData": "1", "Accept": "*/*"},
                timeout=(5, settings.playlist_timeout_seconds),
                stream=True,
            )
            response.raise_for_status()
            response.raw.decode_content = False

            metaint_header = response.headers.get("icy-metaint")
            if not metaint_header:
                return _icy_fallback(station, resolved_url)

            try:
                metaint = int(metaint_header)
            except ValueError:
                return _icy_fallback(station, resolved_url)

            if metaint <= 0 or metaint > 1024 * 1024:
                return _icy_fallback(station, resolved_url)

            raw = response.raw
            for _ in range(3):
                audio_chunk = raw.read(metaint)
                if not audio_chunk or len(audio_chunk) < metaint:
                    break

                metadata_length_byte = raw.read(1)
                if not metadata_length_byte:
                    break

                metadata_length = metadata_length_byte[0] * 16
                if metadata_length <= 0:
                    continue

                metadata_bytes = raw.read(metadata_length)
                if not metadata_bytes:
                    break

                stream_title = _parse_icy_stream_title(metadata_bytes)
                if not stream_title:
                    continue

                artist, title = _split_stream_title(stream_title, station)
                return NowPlaying(
                    played_at=None,
                    artist=artist,
                    title=title,
                    source_url=resolved_url,
                    provider_cover_candidates=(),
                )
        except Exception:
            return _icy_fallback(station, resolved_url)
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass

        return _icy_fallback(station, resolved_url)

    @staticmethod
    def parse_on_playlist_html(html: str, base_url: str | None = None) -> NowPlaying:
        soup = BeautifulSoup(html, "html.parser")
        lines = list(_visible_lines(soup.get_text("\n")))

        stream_idx = 0
        for index, line in enumerate(lines):
            if line.casefold() == "stream":
                stream_idx = index + 1
                break

        for index in range(stream_idx, len(lines) - 2):
            current = _normalize_played_at(lines[index])
            if current is None:
                continue

            artist = _cleanup_track_field(lines[index + 1])
            title = _cleanup_track_field(lines[index + 2])
            if _looks_like_track(artist, title):
                return NowPlaying(
                    played_at=current,
                    artist=artist,
                    title=title,
                    source_url="",
                    provider_cover_candidates=_find_cover_near_track(
                        soup,
                        artist=artist,
                        title=title,
                        played_at=current,
                        base_url=base_url,
                    ),
                )

        raise ValueError("Auf der Playlist-Seite konnte kein aktueller Titel gefunden werden.")

    @staticmethod
    def parse_0nradio_json(payload: Any, base_url: str | None = None) -> NowPlaying:
        current = _extract_onradio_current_node(payload)
        if current is None:
            raise ValueError("Im 0N Radio JSON konnte kein aktueller Titel gefunden werden.")

        artist = _extract_first_text(current, "artist", "artist_name", "artistName", "interpret")
        title = _extract_first_text(current, "title", "song_title", "songTitle", "track")
        played_at = _normalize_played_at(
            _extract_first_text(current, "played", "played_at", "playedAt", "time")
        )
        if not _looks_like_track(artist, title):
            raise ValueError("Das 0N Radio JSON hat keinen gueltigen aktuellen Titel geliefert.")

        candidates = list(_extract_cover_candidates_from_api_node(current, base_url))
        if isinstance(payload, dict):
            candidates.extend(_extract_cover_candidates_from_api_node(payload, base_url))

        return NowPlaying(
            played_at=played_at,
            artist=artist,
            title=title,
            source_url="",
            provider_cover_candidates=tuple(_dedupe_urls(candidates)),
        )

    @staticmethod
    def parse_80s80s_stream_page_html(
        html: str,
        expected_station_labels: tuple[str, ...] = (),
        base_url: str | None = None,
    ) -> NowPlaying:
        soup = BeautifulSoup(html, "html.parser")
        lines = list(_visible_lines(soup.get_text("\n")))
        normalized_labels = {
            _normalize_text(label)
            for label in expected_station_labels
            if _normalize_text(label)
        }

        if normalized_labels:
            for index in range(len(lines) - 2):
                if _normalize_text(lines[index]) not in normalized_labels:
                    continue
                artist = _cleanup_track_field(lines[index + 1])
                title = _cleanup_track_field(lines[index + 2])
                if _looks_like_track(artist, title):
                    return NowPlaying(
                        played_at=None,
                        artist=artist,
                        title=title,
                        source_url="",
                        provider_cover_candidates=_find_cover_near_track(
                            soup,
                            artist=artist,
                            title=title,
                            played_at=None,
                            base_url=base_url,
                        ),
                    )

        for index, line in enumerate(lines):
            normalized_line = _normalize_text(line)
            if not normalized_line.startswith("jetzt horen") and not normalized_line.startswith("es laeuft"):
                continue
            for offset in range(index + 1, min(index + 8, len(lines) - 1)):
                artist = _cleanup_track_field(lines[offset])
                title = _cleanup_track_field(lines[offset + 1])
                if _looks_like_track(artist, title):
                    return NowPlaying(
                        played_at=None,
                        artist=artist,
                        title=title,
                        source_url="",
                        provider_cover_candidates=_find_cover_near_track(
                            soup,
                            artist=artist,
                            title=title,
                            played_at=None,
                            base_url=base_url,
                        ),
                    )

        raise ValueError("Auf der 80s80s-Seite konnte kein aktueller Titel gefunden werden.")


def _expected_station_labels(station: Station) -> tuple[str, ...]:
    labels: list[str] = []
    if station.metadata_station_label:
        labels.append(station.metadata_station_label)
    labels.extend(station.metadata_station_aliases)
    if station.name:
        labels.append(station.name)
    seen: set[str] = set()
    result: list[str] = []
    for value in labels:
        key = value.casefold().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return tuple(result)


def _visible_lines(text: str) -> Iterable[str]:
    for raw in text.splitlines():
        line = SEPARATOR_RE.sub(" ", raw).strip()
        if not line:
            continue
        yield line


def _cleanup_track_field(value: str) -> str:
    cleaned = value.strip().replace("\x92", "'")
    return re.sub(r"\s+", " ", cleaned)


def _looks_like_track(artist: str, title: str) -> bool:
    blocked_prefixes = (
        "Datenschutz",
        "Disclaimer",
        "Impressum",
        "TuneIn",
        "radio.de",
        "vTuner",
        "amazon Alexa",
        "Playlist",
        "Songsuche",
        "Das ist die 80s80s App",
        "mehr lesen",
        "Auch interessant",
        "Radios",
        "Sender",
        "Service",
        "Home",
        "Kontakt",
    )
    if len(artist) < 2 or len(title) < 1:
        return False
    if TIME_RE.fullmatch(artist) or TIME_RE.fullmatch(title):
        return False
    if artist.startswith("Image:") or title.startswith("Image:"):
        return False
    return not any(artist.startswith(prefix) or title.startswith(prefix) for prefix in blocked_prefixes)


def _normalize_played_at(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    match = re.search(r"(\d{1,2}:\d{2})", text)
    if not match:
        return None
    return f"{match.group(1)} Uhr"


def _extract_first_text(node: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = node.get(key)
        if value is None:
            continue
        text = _cleanup_track_field(str(value))
        if text:
            return text
    return ""


def _extract_cover_candidates_from_api_node(node: dict[str, Any], base_url: str | None = None) -> tuple[str, ...]:
    candidates: list[str] = []
    covers = node.get("covers")
    if isinstance(covers, dict):
        for key in (
            "cover_art_url_xxl",
            "cover_art_url_xl",
            "cover_art_url_l",
            "cover_art_url_m",
            "cover_art_url_s",
            "cover_art_url_xs",
            "cover_art_url_custom",
        ):
            resolved = _normalize_image_url(covers.get(key), base_url)
            if resolved:
                candidates.append(resolved)

    for key in (
        "cover",
        "cover_url",
        "coverUrl",
        "image",
        "image_url",
        "imageUrl",
        "artwork_url",
        "artworkUrl",
        "album_cover",
        "albumCover",
    ):
        resolved = _normalize_image_url(node.get(key), base_url)
        if resolved:
            candidates.append(resolved)

    return tuple(_dedupe_urls(candidates))


def _find_cover_near_track(
    soup: BeautifulSoup,
    *,
    artist: str,
    title: str,
    played_at: str | None,
    base_url: str | None,
) -> tuple[str, ...]:
    expected_artist = _normalize_text(artist)
    expected_title = _normalize_text(title)
    if not expected_artist or not expected_title:
        return ()

    for text_node in soup.find_all(string=True):
        text = _cleanup_track_field(str(text_node))
        if not text:
            continue

        matches_anchor = False
        if played_at is not None and _normalize_played_at(text) == played_at:
            matches_anchor = True
        elif _normalize_text(text) in {expected_artist, expected_title}:
            matches_anchor = True

        if not matches_anchor or text_node.parent is None:
            continue

        for ancestor in [text_node.parent, *list(text_node.parent.parents)[:5]]:
            row_texts = [_cleanup_track_field(value) for value in ancestor.stripped_strings]
            if len(row_texts) < 2 or len(row_texts) > 12:
                continue

            normalized_values = {_normalize_text(value) for value in row_texts}
            if expected_artist not in normalized_values or expected_title not in normalized_values:
                continue

            image_urls = _extract_image_urls(ancestor, base_url)
            if image_urls:
                return image_urls

    return ()


def _extract_image_urls(node: Any, base_url: str | None) -> tuple[str, ...]:
    candidates: list[str] = []
    for tag in node.find_all(["img", "source"]):
        for attr in ("src", "data-src", "data-original", "data-lazy-src", "srcset", "data-srcset"):
            raw_value = tag.get(attr)
            resolved = _normalize_image_url(raw_value, base_url)
            if resolved:
                candidates.append(resolved)
    return tuple(_dedupe_urls(candidates))


def _normalize_image_url(raw_value: Any, base_url: str | None) -> str | None:
    if raw_value is None:
        return None
    value = str(raw_value).strip()
    if not value:
        return None
    if "," in value and " " in value:
        value = value.split(",", 1)[0].strip()
    if " " in value:
        value = value.split(" ", 1)[0].strip()
    if value.startswith("data:"):
        return None
    if value.startswith("//"):
        return f"https:{value}"
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if base_url:
        return urljoin(base_url, value)
    return None


def _dedupe_urls(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(key)
    return result


def _find_80s80s_station_entry(
    payload: Any,
    *,
    expected_station_labels: tuple[str, ...],
    expected_station_id: int | None,
) -> dict[str, Any] | None:
    best_score = -1.0
    best_node: dict[str, Any] | None = None
    normalized_expected_labels = tuple(
        label for label in (_normalize_text(value) for value in expected_station_labels) if label
    )

    for node in _iter_dict_nodes(payload):
        artist = _extract_first_text(node, "artist_name", "artist", "artistName")
        title = _extract_first_text(node, "song_title", "title", "songTitle")
        if not _looks_like_track(artist, title):
            continue

        score = 1.0
        station_id = node.get("station_id") or node.get("stationId") or node.get("id")
        if expected_station_id is not None and str(station_id) == str(expected_station_id):
            score += 6.0

        labels = [
            node.get("stream"),
            node.get("stream_name"),
            node.get("streamName"),
            node.get("station"),
            node.get("station_name"),
            node.get("stationName"),
            node.get("channel"),
            node.get("channel_name"),
            node.get("channelName"),
            node.get("name"),
            node.get("label"),
            node.get("title"),
        ]
        normalized_labels = [_normalize_text(str(value)) for value in labels if value not in (None, "")]
        label_score = 0.0
        for expected in normalized_expected_labels:
            for actual in normalized_labels:
                label_score = max(label_score, _score_label_candidate(expected, actual))
        score += label_score

        if score > best_score:
            best_score = score
            best_node = node

    minimum_score = 3.0 if normalized_expected_labels or expected_station_id is not None else 1.0
    return best_node if best_score >= minimum_score else None


def _score_label_candidate(expected: str, actual: str) -> float:
    if not expected or not actual:
        return 0.0
    if expected == actual:
        return 5.0
    if actual.startswith(expected) or actual.endswith(expected):
        return 4.0
    if expected in actual or actual in expected:
        length_penalty = min(0.75, abs(len(actual) - len(expected)) * 0.03)
        return 3.0 - length_penalty
    ratio = SequenceMatcher(None, expected, actual).ratio()
    if ratio >= 0.9:
        return 2.5
    if ratio >= 0.8:
        return 1.75
    return 0.0


def _extract_onradio_current_node(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        items = payload.get("items")
        if isinstance(items, dict):
            for key in ("current", "now", "now_playing", "playing"):
                node = items.get(key)
                if isinstance(node, dict):
                    return node

        for key in ("current", "now", "now_playing", "playing"):
            node = payload.get(key)
            if isinstance(node, dict):
                return node

    for node in _iter_dict_nodes(payload):
        artist = _extract_first_text(node, "artist", "artist_name", "artistName", "interpret")
        title = _extract_first_text(node, "title", "song_title", "songTitle", "track")
        if _looks_like_track(artist, title):
            return node
    return None


def _iter_dict_nodes(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_dict_nodes(child)
        return
    if isinstance(value, list):
        for item in value:
            yield from _iter_dict_nodes(item)


def _normalize_text(value: str) -> str:
    text = value.casefold()
    text = text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_icy_stream_title(raw_metadata: bytes) -> str | None:
    decoded = raw_metadata.rstrip(b"\0").decode("utf-8", errors="ignore")
    match = ICY_TITLE_RE.search(decoded) or ICY_TITLE_RE_DOUBLE.search(decoded)
    if not match:
        return None
    title = _cleanup_track_field(match.group(1))
    return title or None


def _split_stream_title(stream_title: str, station: Station) -> tuple[str, str]:
    cleaned = _cleanup_track_field(stream_title)
    for separator in (" - ", " – ", " — ", " | ", " ~ "):
        if separator not in cleaned:
            continue
        left, right = cleaned.split(separator, 1)
        artist = _cleanup_track_field(left)
        title = _cleanup_track_field(right)
        if _looks_like_track(artist, title):
            return artist, title
    return station.name, cleaned or "Livestream"


def _icy_fallback(station: Station, source_url: str) -> NowPlaying:
    return NowPlaying(
        played_at=None,
        artist=station.name,
        title="Livestream",
        source_url=source_url,
        provider_cover_candidates=(),
    )


def _format_error(exc: Exception) -> str:
    message = str(exc).strip()
    return message if message else exc.__class__.__name__
