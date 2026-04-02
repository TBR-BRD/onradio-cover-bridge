from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any, Callable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .settings import settings

if TYPE_CHECKING:
    from .playlist_fetcher import NowPlaying
    from .stations import Station

REMIX_HINTS = {
    "remastered",
    "radio edit",
    "single version",
    "album version",
    "mono",
    "stereo",
    "edit",
    "version",
    "mix",
    "live",
}

GENERIC_PROVIDER_PLACEHOLDER_HINTS = (
    "default.jpg",
    "default.png",
    "placeholder",
    "no-cover",
    "nocover",
    "kein-cover",
)

AMAZON_BLOCK_HINTS = (
    "captcha",
    "robot check",
    "automated access",
    "sorry, we just need to make sure you're not a robot",
    "enter the characters you see below",
    "/errors/validatecaptcha",
)

AMAZON_NEGATIVE_HINTS = (
    "karaoke",
    "tribute",
    "cover versions",
    "instrumental",
    "playback",
)

AMAZON_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/134.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
}


@dataclass(frozen=True, slots=True)
class CoverResult:
    url: str
    source: str


@dataclass(frozen=True, slots=True)
class AmazonCandidate:
    title: str
    subtitle: str
    image_url: str | None
    product_url: str | None


@dataclass(frozen=True, slots=True)
class ImagePayload:
    content: bytes
    content_type: str


class PreferredCoverProvider:
    def __init__(self) -> None:
        self.musicbrainz = MusicBrainzCoverProvider()
        self.amazon = AmazonSearchCoverProvider()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": settings.user_agent,
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        })
        self._probe_cache: dict[str, tuple[float, str | None]] = {}
        self._probe_lock = threading.Lock()
        self._image_cache: dict[str, tuple[float, ImagePayload | None]] = {}
        self._image_lock = threading.Lock()

    def find_cover(self, station: Station, now_playing: NowPlaying) -> CoverResult | None:
        provider_result = self._find_provider_cover(station, now_playing)
        if provider_result is not None:
            return provider_result

        amazon_result = self.amazon.find_cover(
            now_playing.artist,
            now_playing.title,
            validate_image_url=self._probe_image_url,
        )
        if amazon_result is not None:
            return amazon_result

        if settings.amazon_musicbrainz_fallback_enabled:
            musicbrainz_result = self.musicbrainz.find_cover(now_playing.artist, now_playing.title)
            if musicbrainz_result is not None:
                validated = self._probe_image_url(musicbrainz_result.url)
                if validated is not None:
                    return CoverResult(url=validated, source=musicbrainz_result.source)
        return None

    def fetch_image_payload(self, url: str) -> ImagePayload | None:
        normalized_url = self._probe_image_url(url)
        if normalized_url is None:
            return None

        now = time.monotonic()
        with self._image_lock:
            cached = self._image_cache.get(normalized_url)
            if cached and cached[0] > now:
                return cached[1]

        payload = self._download_image_payload(normalized_url)
        with self._image_lock:
            self._image_cache[normalized_url] = (time.monotonic() + 1800.0, payload)
        return payload

    def _find_provider_cover(self, station: Station, now_playing: NowPlaying) -> CoverResult | None:
        for candidate_url in now_playing.provider_cover_candidates:
            validated_url = self._probe_image_url(candidate_url)
            if validated_url is None:
                continue
            return CoverResult(
                url=validated_url,
                source=f"{station.name} Stream-Anbieter",
            )
        return None

    def _probe_image_url(self, url: str) -> str | None:
        normalized_url = url.strip()
        if not normalized_url:
            return None
        if self._looks_like_placeholder(normalized_url):
            return None

        now = time.monotonic()
        with self._probe_lock:
            cached = self._probe_cache.get(normalized_url)
            if cached and cached[0] > now:
                return cached[1]

        resolved_url = self._perform_probe(normalized_url)
        with self._probe_lock:
            self._probe_cache[normalized_url] = (time.monotonic() + 1800.0, resolved_url)
        return resolved_url

    def _perform_probe(self, url: str) -> str | None:
        timeout = (5, settings.playlist_timeout_seconds)

        try:
            head_response = self.session.head(
                url,
                allow_redirects=True,
                timeout=timeout,
            )
            try:
                if self._is_image_response(head_response) and not self._looks_like_placeholder(head_response.url):
                    return head_response.url
            finally:
                head_response.close()
        except requests.RequestException:
            pass

        try:
            get_response = self.session.get(
                url,
                allow_redirects=True,
                timeout=timeout,
                stream=True,
            )
            try:
                if not self._is_image_response(get_response):
                    return None
                if self._looks_like_placeholder(get_response.url):
                    return None
                iterator = get_response.iter_content(chunk_size=128)
                next(iterator, b"")
                return get_response.url
            finally:
                get_response.close()
        except requests.RequestException:
            return None

    def _download_image_payload(self, url: str) -> ImagePayload | None:
        timeout = (5, settings.playlist_timeout_seconds)
        try:
            response = self.session.get(
                url,
                allow_redirects=True,
                timeout=timeout,
                stream=True,
            )
            try:
                if not self._is_image_response(response):
                    return None
                if self._looks_like_placeholder(response.url):
                    return None
                content_type = str(response.headers.get("Content-Type") or "image/jpeg").split(";", 1)[0].strip() or "image/jpeg"
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    chunks.append(chunk)
                    total += len(chunk)
                    if total > 5 * 1024 * 1024:
                        return None
                if total == 0:
                    return None
                return ImagePayload(content=b"".join(chunks), content_type=content_type)
            finally:
                response.close()
        except requests.RequestException:
            return None

    @staticmethod
    def _is_image_response(response: requests.Response) -> bool:
        if response.status_code < 200 or response.status_code >= 300:
            return False
        content_type = str(response.headers.get("Content-Type") or "").casefold()
        return content_type.startswith("image/")

    @staticmethod
    def _looks_like_placeholder(url: str) -> bool:
        lowered = url.casefold()
        return any(hint in lowered for hint in GENERIC_PROVIDER_PLACEHOLDER_HINTS)


class AmazonSearchCoverProvider:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(AMAZON_BROWSER_HEADERS)
        self._cache: dict[tuple[str, str], CoverResult | None] = {}
        self._lock = threading.Lock()

    def find_cover(
        self,
        artist: str,
        title: str,
        *,
        validate_image_url: Callable[[str], str | None],
    ) -> CoverResult | None:
        if not settings.amazon_cover_enabled:
            return None

        key = (_normalize_cache_key(artist), _normalize_cache_key(title))
        with self._lock:
            if key in self._cache:
                return self._cache[key]

        result: CoverResult | None = None
        for query in self._build_queries(artist, title):
            try:
                candidates = self._search(query)
            except Exception:
                continue
            best = _pick_best_amazon_candidate(candidates, artist, title)
            if best is None:
                continue

            for image_url in self._image_candidates_for_result(best):
                validated = validate_image_url(image_url)
                if validated is None:
                    continue
                result = CoverResult(
                    url=validated,
                    source=f"Amazon ({settings.amazon_cover_marketplace})",
                )
                break
            if result is not None:
                break

        with self._lock:
            self._cache[key] = result
        return result

    def _build_queries(self, artist: str, title: str) -> list[str]:
        primary_artist = _primary_artist(artist)
        simplified_title = _simplify_title(title)
        values = [
            f'{primary_artist} {simplified_title} cd',
            f'{primary_artist} {simplified_title} vinyl',
            f'{artist} {title} cd',
        ]
        return _dedupe(values)

    def _search(self, query: str) -> list[AmazonCandidate]:
        response = self.session.get(
            f"https://{settings.amazon_cover_marketplace}/s",
            params={"k": query},
            timeout=(5, settings.amazon_cover_timeout_seconds),
        )
        response.raise_for_status()
        html = response.text
        if _looks_like_amazon_block(html):
            raise ValueError("Amazon hat die Cover-Suche voruebergehend blockiert.")
        return self._parse_search_results(html, response.url)

    def _parse_search_results(self, html: str, page_url: str) -> list[AmazonCandidate]:
        soup = BeautifulSoup(html, "html.parser")
        results: list[AmazonCandidate] = []

        for node in soup.select('div[data-component-type="s-search-result"][data-asin]'):
            title = _first_text(node, "h2 span", "a h2 span", "h2 a span")
            if not title:
                continue

            image_url = _first_image_url(node.select_one("img.s-image"), page_url)
            link = node.select_one("h2 a[href]")
            product_url = urljoin(page_url, str(link.get("href"))) if link and link.get("href") else None
            subtitle = " ".join(_visible_strings(node, limit=14))

            results.append(
                AmazonCandidate(
                    title=title,
                    subtitle=subtitle,
                    image_url=image_url,
                    product_url=product_url,
                )
            )

        return results

    def _image_candidates_for_result(self, candidate: AmazonCandidate) -> list[str]:
        urls: list[str] = []
        if candidate.product_url:
            try:
                urls.extend(self._fetch_product_images(candidate.product_url))
            except Exception:
                pass
        if candidate.image_url:
            urls.append(candidate.image_url)
        return _dedupe_urls(urls)

    def _fetch_product_images(self, url: str) -> list[str]:
        response = self.session.get(
            url,
            timeout=(5, settings.amazon_cover_timeout_seconds),
        )
        response.raise_for_status()
        html = response.text
        if _looks_like_amazon_block(html):
            raise ValueError("Amazon hat die Produktseite voruebergehend blockiert.")

        soup = BeautifulSoup(html, "html.parser")
        candidates: list[str] = []

        for selector in ("#landingImage", "#imgTagWrapperId img", "#ebooksImgBlkFront"):
            tag = soup.select_one(selector)
            if tag is None:
                continue
            candidates.extend(_extract_amazon_image_urls_from_tag(tag, response.url))

        for tag in soup.select("img[data-old-hires], img[data-a-dynamic-image]"):
            candidates.extend(_extract_amazon_image_urls_from_tag(tag, response.url))

        return _dedupe_urls(sorted(candidates, key=_amazon_image_sort_key, reverse=True))


class MusicBrainzCoverProvider:
    SEARCH_URL = "https://musicbrainz.org/ws/2/recording"

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": settings.user_agent})
        self._cache: dict[tuple[str, str], CoverResult | None] = {}
        self._rate_lock = threading.Lock()
        self._last_request_ts = 0.0

    def find_cover(self, artist: str, title: str) -> CoverResult | None:
        key = (_normalize_cache_key(artist), _normalize_cache_key(title))
        if key in self._cache:
            return self._cache[key]

        primary_artist = _primary_artist(artist)
        simplified_title = _simplify_title(title)
        queries = _dedupe(
            [
                self._make_query(primary_artist, simplified_title),
                self._make_query(artist, simplified_title),
                self._make_query(primary_artist, title),
            ]
        )

        result: CoverResult | None = None
        for query in queries:
            payload = self._search(query)
            recordings = payload.get("recordings", [])
            match = _pick_best_recording(recordings, artist, title)
            if match is None:
                continue

            release_id = _choose_release_id(match)
            if release_id:
                result = CoverResult(
                    url=f"https://coverartarchive.org/release/{release_id}/front-500",
                    source="MusicBrainz / Cover Art Archive",
                )
                break

        self._cache[key] = result
        return result

    def _search(self, query: str) -> dict[str, Any]:
        self._respect_rate_limit()
        response = self.session.get(
            self.SEARCH_URL,
            params={
                "query": query,
                "fmt": "json",
                "limit": 8,
            },
            timeout=(5, 10),
        )
        response.raise_for_status()
        return response.json()

    def _respect_rate_limit(self) -> None:
        with self._rate_lock:
            now = time.monotonic()
            elapsed = now - self._last_request_ts
            minimum_gap = 1.05
            if elapsed < minimum_gap:
                time.sleep(minimum_gap - elapsed)
            self._last_request_ts = time.monotonic()

    @staticmethod
    def _make_query(artist: str, title: str) -> str:
        safe_artist = _quote_for_musicbrainz(artist)
        safe_title = _quote_for_musicbrainz(title)
        return f'recording:"{safe_title}" AND artist:"{safe_artist}"'



def _pick_best_recording(
    recordings: list[dict[str, Any]],
    expected_artist: str,
    expected_title: str,
) -> dict[str, Any] | None:
    best_score = 0.0
    best_recording: dict[str, Any] | None = None

    norm_expected_artist = _normalize_for_match(_primary_artist(expected_artist))
    norm_expected_title = _normalize_for_match(_simplify_title(expected_title))

    for recording in recordings:
        title = str(recording.get("title") or "")
        artist_credit = _artist_credit_as_text(recording.get("artist-credit", []))
        releases = recording.get("releases") or []
        if not releases:
            continue

        title_score = SequenceMatcher(
            None,
            norm_expected_title,
            _normalize_for_match(_simplify_title(title)),
        ).ratio()
        artist_score = SequenceMatcher(
            None,
            norm_expected_artist,
            _normalize_for_match(_primary_artist(artist_credit)),
        ).ratio()

        raw_score = recording.get("score")
        try:
            mb_score = max(0.0, min(1.0, int(str(raw_score)) / 100.0))
        except (TypeError, ValueError):
            mb_score = 0.0

        total_score = (title_score * 0.55) + (artist_score * 0.25) + (mb_score * 0.20)
        if releases:
            total_score += 0.05

        if total_score > best_score:
            best_score = total_score
            best_recording = recording

    if best_score < 0.67:
        return None
    return best_recording



def _pick_best_amazon_candidate(
    candidates: list[AmazonCandidate],
    expected_artist: str,
    expected_title: str,
) -> AmazonCandidate | None:
    best_score = 0.0
    best_candidate: AmazonCandidate | None = None

    normalized_artist = _normalize_for_match(_primary_artist(expected_artist))
    normalized_title = _normalize_for_match(_simplify_title(expected_title))

    for candidate in candidates:
        combined = _normalize_for_match(f"{candidate.title} {candidate.subtitle}")
        if not combined:
            continue

        title_score = _field_match_score(normalized_title, combined)
        artist_score = _field_match_score(normalized_artist, combined)

        total_score = (title_score * 0.6) + (artist_score * 0.35)
        if "audio cd" in combined or "vinyl" in combined or "musik cd" in combined:
            total_score += 0.1
        if any(hint in combined for hint in AMAZON_NEGATIVE_HINTS):
            total_score -= 0.25

        if total_score > best_score:
            best_score = total_score
            best_candidate = candidate

    if best_score < 0.62:
        return None
    return best_candidate



def _field_match_score(expected: str, actual: str) -> float:
    if not expected or not actual:
        return 0.0
    if expected == actual:
        return 1.0
    if expected in actual:
        length_penalty = min(0.25, max(0, len(actual) - len(expected)) * 0.01)
        return 0.92 - length_penalty
    return SequenceMatcher(None, expected, actual).ratio()



def _choose_release_id(recording: dict[str, Any]) -> str | None:
    releases = recording.get("releases") or []
    if not releases:
        return None

    official = [release for release in releases if str(release.get("status") or "").casefold() == "official"]
    for release in official + releases:
        release_id = release.get("id")
        if isinstance(release_id, str) and release_id:
            return release_id
    return None



def _artist_credit_as_text(artist_credit: list[Any]) -> str:
    parts: list[str] = []
    for item in artist_credit:
        if isinstance(item, dict):
            parts.append(str(item.get("name") or item.get("artist", {}).get("name") or ""))
        elif isinstance(item, str):
            parts.append(item)
    return " ".join(part.strip() for part in parts if str(part).strip())



def _primary_artist(value: str) -> str:
    tokens = re.split(r"\s*(?:,|feat\.?|ft\.?|featuring|&| x | und )\s*", value, maxsplit=1, flags=re.IGNORECASE)
    return tokens[0].strip() if tokens else value.strip()



def _simplify_title(value: str) -> str:
    text = value.strip()
    text = re.sub(r"[\[\(].*?[\]\)]", _replace_if_version_hint, text)
    text = re.sub(r"\s+-\s+(Remastered.*|Radio Edit|Single Version|Album Version)$", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip(" -")



def _replace_if_version_hint(match: re.Match[str]) -> str:
    content = match.group(0).strip("[]() ").casefold()
    if any(hint in content for hint in REMIX_HINTS):
        return ""
    return match.group(0)



def _quote_for_musicbrainz(value: str) -> str:
    return value.replace('\\', ' ').replace('"', ' ')



def _normalize_cache_key(value: str) -> str:
    return _normalize_for_match(value)



def _normalize_for_match(value: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(ch for ch in ascii_text if not unicodedata.combining(ch))
    ascii_text = ascii_text.casefold()
    ascii_text = re.sub(r"[^a-z0-9]+", " ", ascii_text)
    return re.sub(r"\s+", " ", ascii_text).strip()



def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.casefold().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result



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



def _looks_like_amazon_block(html: str) -> bool:
    lowered = html.casefold()
    return any(hint in lowered for hint in AMAZON_BLOCK_HINTS)



def _visible_strings(node: Any, *, limit: int) -> list[str]:
    result: list[str] = []
    for text in node.stripped_strings:
        normalized = re.sub(r"\s+", " ", str(text)).strip()
        if not normalized:
            continue
        result.append(normalized)
        if len(result) >= limit:
            break
    return result



def _first_text(node: Any, *selectors: str) -> str:
    for selector in selectors:
        match = node.select_one(selector)
        if match is None:
            continue
        text = re.sub(r"\s+", " ", match.get_text(" ", strip=True)).strip()
        if text:
            return text
    return ""



def _first_image_url(tag: Any, base_url: str) -> str | None:
    if tag is None:
        return None
    for url in _extract_amazon_image_urls_from_tag(tag, base_url):
        return url
    return None



def _extract_amazon_image_urls_from_tag(tag: Any, base_url: str) -> list[str]:
    candidates: list[str] = []

    data_old_hires = str(tag.get("data-old-hires") or "").strip()
    if data_old_hires:
        candidates.append(urljoin(base_url, data_old_hires))

    dynamic_image = tag.get("data-a-dynamic-image")
    if dynamic_image:
        try:
            payload = json.loads(dynamic_image)
            if isinstance(payload, dict):
                for raw_url in payload.keys():
                    if isinstance(raw_url, str) and raw_url.strip():
                        candidates.append(urljoin(base_url, raw_url.strip()))
        except json.JSONDecodeError:
            pass

    for attr in ("src", "data-src", "data-image-latency-source"):
        raw = str(tag.get(attr) or "").strip()
        if raw:
            candidates.append(urljoin(base_url, raw))

    srcset = str(tag.get("srcset") or "").strip()
    if srcset:
        for part in srcset.split(","):
            item = part.strip().split(" ", 1)[0].strip()
            if item:
                candidates.append(urljoin(base_url, item))

    return _dedupe_urls(candidates)



def _amazon_image_sort_key(url: str) -> tuple[int, int]:
    for pattern in (r"_SL(\d+)_", r"_SX(\d+)_", r"_SY(\d+)_", r"_AC_UL(\d+)_", r"_AC_UY(\d+)_"):
        match = re.search(pattern, url)
        if match:
            size = int(match.group(1))
            return (size, len(url))
    return (0, len(url))
