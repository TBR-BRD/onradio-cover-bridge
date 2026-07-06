from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, unquote, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from .settings import settings


URL_RE = re.compile(r"https?://[^\s\"'<>\\)]+", re.IGNORECASE)
STREAM_HINT_RE = re.compile(
    r"(^|[-_/])(aacp?|mp3|ogg|opus|flac|stream|streams|live|listen|webradio|radio|playlist)([-_/]|$)",
    re.IGNORECASE,
)
DIRECT_AUDIO_EXTENSIONS = {".mp3", ".aac", ".ogg", ".opus", ".flac", ".wav"}
PLAYLIST_EXTENSIONS = {
    ".pls": "pls",
    ".m3u": "m3u",
    ".m3u8": "m3u",
}
IGNORED_EXTENSIONS = {
    ".css",
    ".js",
    ".json",
    ".xml",
    ".html",
    ".htm",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
}


@dataclass(frozen=True, slots=True)
class StreamCandidate:
    name: str
    homepage_url: str
    audio_url: str
    audio_mode: str
    source: str
    confidence: str

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "homepage_url": self.homepage_url,
            "audio_url": self.audio_url,
            "audio_mode": self.audio_mode,
            "source": self.source,
            "confidence": self.confidence,
        }


def discover_streams(page_url: str, *, limit: int = 150) -> dict[str, Any]:
    page_url = _clean_page_url(page_url)
    page_host = _host_key(page_url)
    response = requests.get(
        page_url,
        timeout=(5, settings.playlist_timeout_seconds),
        headers={"User-Agent": settings.user_agent, "Accept": "text/html,application/xhtml+xml,*/*"},
    )
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "")
    text = response.text[:2_500_000]
    soup = BeautifulSoup(text, "html.parser")
    page_title = _page_title(soup, page_url)

    seen: set[str] = set()
    candidates: list[StreamCandidate] = []
    for candidate in _structured_channel_candidates(soup, text, page_url, page_title):
        if candidate.audio_url in seen:
            continue
        seen.add(candidate.audio_url)
        candidates.append(candidate)
        if len(candidates) >= limit:
            break

    for raw_url, label, source, strong_source in _extract_urls(soup, text, page_url):
        if len(candidates) >= limit:
            break
        stream_url = _normalize_stream_url(raw_url)
        if not stream_url or stream_url in seen:
            continue
        mode = _audio_mode_for_url(stream_url, strong_source=strong_source, page_host=page_host)
        if mode is None:
            continue
        if not strong_source and not _has_audio_extension(stream_url) and not _probe_stream_candidate(stream_url):
            continue
        seen.add(stream_url)
        candidates.append(
            StreamCandidate(
                name=_candidate_name(label=label, page_title=page_title, stream_url=stream_url, index=len(candidates) + 1),
                homepage_url=page_url,
                audio_url=stream_url,
                audio_mode=mode,
                source=source,
                confidence="hoch" if strong_source or _has_audio_extension(stream_url) else "moeglich",
            )
        )

    return {
        "source_url": page_url,
        "title": page_title,
        "content_type": content_type,
        "candidates": [candidate.to_public_dict() for candidate in candidates],
    }


def _structured_channel_candidates(soup: BeautifulSoup, raw_html: str, page_url: str, page_title: str) -> list[StreamCandidate]:
    host_key = _host_key(page_url)
    if host_key == "sunshine-live.de":
        candidates = _sunshine_live_candidates(raw_html, page_url)
        if len(candidates) >= 5 or urlparse(page_url).path.rstrip("/") == "/music/channels":
            return candidates
        try:
            response = requests.get(
                "https://www.sunshine-live.de/music/channels",
                timeout=(5, settings.playlist_timeout_seconds),
                headers={"User-Agent": settings.user_agent, "Accept": "text/html,application/xhtml+xml,*/*"},
            )
            response.raise_for_status()
        except requests.RequestException:
            return candidates
        return _sunshine_live_candidates(response.text[:2_500_000], "https://www.sunshine-live.de/music/channels")

    if host_key == "80s80s.de":
        candidates = _eighties_candidates(raw_html, page_url)
        if len(candidates) >= 10 or urlparse(page_url).path.rstrip("/") == "/streams":
            return candidates
        try:
            response = requests.get(
                "https://www.80s80s.de/streams",
                timeout=(5, settings.playlist_timeout_seconds),
                headers={"User-Agent": settings.user_agent, "Accept": "text/html,application/xhtml+xml,*/*"},
            )
            response.raise_for_status()
        except requests.RequestException:
            return candidates
        return _eighties_candidates(response.text[:2_500_000], "https://www.80s80s.de/streams")

    if host_key != "antenne.de":
        return []

    candidates: list[StreamCandidate] = []
    seen_keys: set[str] = set()
    for play_button in soup.select('[data-play-type="channel"][data-play]'):
        channel_key = _safe_channel_key(play_button.get("data-play"))
        if not channel_key or channel_key in seen_keys:
            continue
        seen_keys.add(channel_key)

        card = _nearest_card(play_button)
        name = _antenne_channel_name(card, channel_key, page_title)
        homepage_url = _antenne_channel_homepage(card, page_url, channel_key)
        audio_url = f"https://play.antenne.de/{channel_key}.m3u"
        if not _probe_stream_candidate(audio_url):
            continue
        candidates.append(
            StreamCandidate(
                name=name,
                homepage_url=homepage_url,
                audio_url=audio_url,
                audio_mode="m3u",
                source="antenne.channel",
                confidence="hoch",
            )
        )
    return candidates


def _sunshine_live_candidates(raw_html: str, page_url: str) -> list[StreamCandidate]:
    pattern = re.compile(r'stream:"([^"]+)"(?:(?!stream:").){0,2500}?url_high:"([^"]+)"', re.DOTALL)
    candidates: list[StreamCandidate] = []
    seen_urls: set[str] = set()
    for raw_name, raw_url in pattern.findall(raw_html):
        name = _decode_js_string(raw_name)
        stream_url = _normalize_sunshine_stream_url(_decode_js_string(raw_url))
        if not name or not stream_url or stream_url in seen_urls:
            continue
        seen_urls.add(stream_url)
        candidates.append(
            StreamCandidate(
                name=f"Sunshine Live {name}" if not name.casefold().startswith("sunshine live") else name,
                homepage_url=page_url,
                audio_url=stream_url,
                audio_mode="direct",
                source="sunshine.nuxt",
                confidence="hoch",
            )
        )
    return candidates


def _eighties_candidates(raw_html: str, page_url: str) -> list[StreamCandidate]:
    pattern = re.compile(r'stream:"([^"]+)"(?:(?!stream:").){0,2500}?url_high:"([^"]+)"', re.DOTALL)
    candidates: list[StreamCandidate] = []
    seen_urls: set[str] = set()
    for raw_name, raw_url in pattern.findall(raw_html):
        name = _decode_js_string(raw_name)
        stream_url = _normalize_eighties_stream_url(_decode_js_string(raw_url))
        if not name or not stream_url or stream_url in seen_urls:
            continue
        seen_urls.add(stream_url)
        candidates.append(
            StreamCandidate(
                name=name if name.casefold().startswith("80s80s") else f"80s80s {name}",
                homepage_url=page_url,
                audio_url=stream_url,
                audio_mode="direct",
                source="80s80s.nuxt",
                confidence="hoch",
            )
        )
    return candidates


def _decode_js_string(value: str) -> str:
    try:
        decoded = json.loads(f'"{value}"')
    except json.JSONDecodeError:
        decoded = value.replace(r"\u002F", "/").replace(r"\/", "/")
    return _visible_label(html.unescape(decoded))


def _normalize_sunshine_stream_url(value: str) -> str:
    url = value.strip()
    if url.startswith("//"):
        url = f"https:{url}"
    elif url.startswith("http://"):
        url = f"https://{url[7:]}"
    if not url.startswith("https://stream.sunshine-live.de/"):
        return ""
    return url


def _normalize_eighties_stream_url(value: str) -> str:
    url = value.strip()
    if url.startswith("//"):
        url = f"https:{url}"
    elif url.startswith("http://"):
        url = f"https://{url[7:]}"
    if not url.startswith("https://streams.80s80s.de/"):
        return ""
    return url


def _extract_urls(soup: BeautifulSoup, raw_html: str, base_url: str) -> list[tuple[str, str, str, bool]]:
    extracted: list[tuple[str, str, str, bool]] = []
    for tag in soup.find_all(["a", "audio", "source", "iframe", "embed", "link", "meta"]):
        label = _visible_label(tag.get_text(" ", strip=True))
        tag_name = getattr(tag, "name", "tag")
        for attr in ("href", "src", "data-src", "content"):
            value = tag.get(attr)
            if not isinstance(value, str) or not value.strip():
                continue
            url = _resolve_embedded_url(value.strip(), base_url)
            if url:
                strong_source = tag_name in {"audio", "source"} or _has_audio_extension(url)
                extracted.append((url, label, f"{tag_name}.{attr}", strong_source))

    for match in URL_RE.finditer(html.unescape(raw_html)):
        extracted.append((_trim_url(match.group(0)), "", "html", False))
    return extracted


def _nearest_card(tag: Any) -> Any:
    current = tag
    for _ in range(10):
        if current is None:
            return tag
        class_name = " ".join(current.get("class") or []) if hasattr(current, "get") else ""
        if "audiocard" in class_name or current.get("data-cardgriditem") is not None:
            return current
        current = current.parent
    return tag


def _antenne_channel_name(card: Any, channel_key: str, page_title: str) -> str:
    share = card.select_one("[data-sharetitle]") if hasattr(card, "select_one") else None
    if share is not None:
        name = _visible_label(share.get("data-sharetitle"))
        if name:
            return name[:80]
    headline = card.select_one("h2, h3, h4, .c-audiocard__title") if hasattr(card, "select_one") else None
    if headline is not None:
        name = _visible_label(headline.get_text(" ", strip=True))
        if name:
            return name[:80]
    return f"{page_title} - {channel_key.replace('-', ' ').title()}"[:80]


def _antenne_channel_homepage(card: Any, page_url: str, channel_key: str) -> str:
    share = card.select_one("[data-shareurl]") if hasattr(card, "select_one") else None
    if share is not None:
        url = _resolve_embedded_url(str(share.get("data-shareurl") or ""), page_url)
        if url:
            return url
    link = card.select_one("a[href*='/webradio/']") if hasattr(card, "select_one") else None
    if link is not None:
        url = _resolve_embedded_url(str(link.get("href") or ""), page_url)
        if url:
            return url
    return urljoin(page_url, f"/webradio/{channel_key}")


def _safe_channel_key(value: Any) -> str:
    key = str(value or "").strip()
    if re.fullmatch(r"[a-z0-9][a-z0-9-]{1,80}", key):
        return key
    return ""


def _clean_page_url(value: str) -> str:
    url = str(value or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Bitte eine gueltige HTTP- oder HTTPS-URL eingeben.")
    return url


def _resolve_embedded_url(value: str, base_url: str) -> str:
    value = html.unescape(value).strip()
    if not value:
        return ""
    if value.startswith("//"):
        parsed_base = urlparse(base_url)
        value = f"{parsed_base.scheme}:{value}"
    if value.startswith(("http://", "https://")):
        resolved = _trim_url(value)
        return _nested_stream_url(resolved) or resolved
    if value.startswith(("/", "./", "../")):
        resolved = _trim_url(urljoin(base_url, value))
        return _nested_stream_url(resolved) or resolved
    nested = _nested_stream_url(value)
    return nested or ""


def _nested_stream_url(value: str) -> str:
    parsed = urlparse(value)
    query = parse_qs(parsed.query)
    for key in ("url", "u", "stream", "src", "source"):
        for item in query.get(key, ()):
            decoded = unquote(item)
            if decoded.startswith(("http://", "https://")):
                return _trim_url(decoded)
    return ""


def _normalize_stream_url(value: str) -> str:
    url = _trim_url(value)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", parsed.query, ""))


def _audio_mode_for_url(url: str, *, strong_source: bool, page_host: str) -> str | None:
    parsed = urlparse(url)
    path = parsed.path.casefold()
    extension = _path_extension(path)
    if extension in PLAYLIST_EXTENSIONS:
        return PLAYLIST_EXTENSIONS[extension]
    if extension in DIRECT_AUDIO_EXTENSIONS:
        return "direct"
    if extension in IGNORED_EXTENSIONS:
        return None
    if strong_source:
        return "direct"
    if _host_key(url) == page_host:
        return None
    if "stream" in parsed.netloc.casefold() or STREAM_HINT_RE.search(path):
        return "direct"
    return None


def _candidate_name(*, label: str, page_title: str, stream_url: str, index: int) -> str:
    label = _visible_label(label)
    if label and not label.startswith(("http://", "https://")) and len(label) >= 3:
        return label[:80]
    parsed = urlparse(stream_url)
    parts = [part for part in parsed.path.split("/") if part]
    suffix = parts[-1] if parts else parsed.netloc
    suffix = re.sub(r"\.(mp3|aac|ogg|opus|flac|wav|pls|m3u8?)$", "", suffix, flags=re.IGNORECASE)
    suffix = re.sub(r"[-_]+", " ", suffix).strip()
    if suffix and suffix.casefold() not in {"stream", "live", "listen"}:
        return f"{page_title} - {suffix}"[:80]
    return f"{page_title} Stream {index}"[:80]


def _page_title(soup: BeautifulSoup, page_url: str) -> str:
    candidates = [
        soup.find("meta", attrs={"property": "og:site_name"}),
        soup.find("meta", attrs={"property": "og:title"}),
        soup.find("title"),
    ]
    for tag in candidates:
        if tag is None:
            continue
        value = tag.get("content") if tag.name == "meta" else tag.get_text(" ", strip=True)
        title = _visible_label(value)
        if title:
            return title[:80]
    return urlparse(page_url).netloc


def _visible_label(value: Any) -> str:
    return " ".join(str(value or "").split())


def _has_audio_extension(url: str) -> bool:
    extension = _path_extension(urlparse(url).path.casefold())
    return extension in DIRECT_AUDIO_EXTENSIONS or extension in PLAYLIST_EXTENSIONS


def _path_extension(path: str) -> str:
    match = re.search(r"(\.[a-z0-9]{2,5})$", path)
    return match.group(1) if match else ""


def _host_key(url: str) -> str:
    host = urlparse(url).netloc.casefold()
    return host[4:] if host.startswith("www.") else host


def _probe_stream_candidate(url: str) -> bool:
    try:
        response = requests.get(
            url,
            stream=True,
            allow_redirects=True,
            timeout=(3, 4),
            headers={"User-Agent": settings.user_agent, "Accept": "*/*", "Range": "bytes=0-65535"},
        )
    except requests.RequestException:
        return False
    try:
        if response.status_code >= 400:
            return False
        content_type = (response.headers.get("Content-Type") or "").casefold()
        if "text/html" in content_type:
            return False
        if _path_extension(urlparse(url).path.casefold()) in PLAYLIST_EXTENSIONS:
            return _probe_playlist_response(response)
        if content_type.startswith("audio/"):
            return True
        if any(marker in content_type for marker in ("mpegurl", "x-scpls", "octet-stream")):
            return True
        return not content_type
    finally:
        response.close()


def _probe_playlist_response(response: requests.Response) -> bool:
    try:
        payload = b""
        for chunk in response.iter_content(chunk_size=4096):
            if not chunk:
                continue
            payload += chunk
            if len(payload) >= 65536:
                break
    except requests.RequestException:
        return False
    text = payload.decode(response.encoding or "utf-8", errors="ignore")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("["):
            continue
        if line.startswith(("File", "file")) and "=" in line:
            line = line.split("=", 1)[1].strip()
        return line.startswith(("http://", "https://"))
    return False


def _trim_url(url: str) -> str:
    return url.strip().rstrip(".,;)'\"\\]")
