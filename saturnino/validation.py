from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlsplit

from .models import MediaCandidate, ValidationResult
from .scoring import classify_media_type, normalize_content_type

MAX_MANIFEST_BYTES = 256 * 1024
MAX_DIRECT_BYTES = 4 * 1024
MAX_REDIRECTS = 5


async def validate_candidate(candidate: MediaCandidate, timeout: float = 8.0) -> ValidationResult:
    """Validate without retaining an entire media representation in memory."""
    try:
        import httpx
    except ImportError:
        return ValidationResult("inconclusive", "httpx is not installed", candidate.url)

    if not candidate.url.startswith(("http://", "https://")):
        return ValidationResult("invalid", "unsupported URL scheme", candidate.url)
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(
            follow_redirects=False,
            headers={"Accept-Encoding": "identity", "User-Agent": "saturnino/0.1"},
        ) as client:
            if candidate.media_type in {"mp4", "webm", "mkv", "unknown"}:
                result = await _validate_direct(client, candidate, timeout, started)
            else:
                result = await _validate_manifest(client, candidate, timeout, started)
            return result
    except httpx.TimeoutException:
        return ValidationResult("inconclusive", "validation timed out", candidate.url)
    except httpx.HTTPError as exc:
        return ValidationResult("inconclusive", f"validation transport error: {type(exc).__name__}", candidate.url)
    except Exception as exc:
        return ValidationResult("inconclusive", f"validation failed: {type(exc).__name__}", candidate.url)


async def _validate_manifest(client, candidate: MediaCandidate, timeout: float, started: float) -> ValidationResult:
    response, body, truncated = await _bounded_get(client, candidate.url, timeout, started, MAX_MANIFEST_BYTES)
    if response is None:
        return ValidationResult("inconclusive", "no response", candidate.url)
    content_type = normalize_content_type(response.headers.get("content-type"))
    if response.status_code < 200 or response.status_code >= 300:
        return ValidationResult("invalid", f"HTTP {response.status_code}", candidate.url, response.url, response.status_code)
    text = body.decode("utf-8-sig", errors="replace").lstrip()
    if candidate.media_type == "hls":
        if not text.startswith("#EXTM3U"):
            return ValidationResult("invalid", "response is not an M3U8 playlist", candidate.url, response.url, response.status_code)
        has_structure = any(marker in text for marker in ("#EXTINF", "#EXT-X-STREAM-INF", "#EXT-X-MEDIA", "#EXT-X-PART"))
        if not has_structure:
            return ValidationResult("invalid", "M3U8 marker lacks playlist structure", candidate.url, response.url, response.status_code)
        reason = "valid HLS playlist" + (" (bounded sample)" if truncated else "")
        return ValidationResult("valid", reason, candidate.url, response.url, response.status_code)

    if candidate.media_type == "dash":
        if truncated:
            return ValidationResult("inconclusive", "DASH document exceeded validation bound", candidate.url, response.url, response.status_code)
        try:
            root = ET.fromstring(body)
        except ET.ParseError:
            return ValidationResult("invalid", "response is not valid DASH XML", candidate.url, response.url, response.status_code)
        if root.tag.rsplit("}", 1)[-1] != "MPD":
            return ValidationResult("invalid", "XML root is not MPD", candidate.url, response.url, response.status_code)
        return ValidationResult("valid", "valid DASH manifest", candidate.url, response.url, response.status_code)

    return ValidationResult("inconclusive", f"unclassified content type {content_type or 'unknown'}", candidate.url, response.url, response.status_code)


async def _validate_direct(client, candidate: MediaCandidate, timeout: float, started: float) -> ValidationResult:
    response, final_url = await _head(client, candidate.url, timeout, started)
    if response is not None and 200 <= response.status_code < 300 and response.status_code != 204:
        mime = normalize_content_type(response.headers.get("content-type"))
        if mime in {"text/html", "application/json"}:
            return ValidationResult("invalid", "HEAD response is an error document", candidate.url, final_url, response.status_code)
        return ValidationResult("valid", "direct-media headers accepted", candidate.url, final_url, response.status_code)

    response, body, _ = await _bounded_get(client, candidate.url, timeout, started, MAX_DIRECT_BYTES, range_request=True)
    if response is None:
        return ValidationResult("inconclusive", "no response", candidate.url)
    mime = normalize_content_type(response.headers.get("content-type"))
    if response.status_code < 200 or response.status_code >= 300 or response.status_code == 204:
        state = "invalid" if response.status_code in {401, 403, 404, 410} else "inconclusive"
        return ValidationResult(state, f"HTTP {response.status_code}", candidate.url, response.url, response.status_code)
    if mime in {"text/html", "application/json"}:
        return ValidationResult("invalid", "response is an error document", candidate.url, response.url, response.status_code)
    if mime.startswith("video/") or classify_media_type(response.url, mime) != "unknown" or body:
        return ValidationResult("valid", "direct-media response accepted", candidate.url, response.url, response.status_code)
    return ValidationResult("inconclusive", "direct-media response has no usable media evidence", candidate.url, response.url, response.status_code)


async def _head(client, url: str, timeout: float, started: float):
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        remaining = _remaining(timeout, started)
        if remaining <= 0:
            return None, current
        response = await client.head(current, timeout=max(0.1, remaining))
        if response.status_code not in {301, 302, 303, 307, 308}:
            return response, str(response.url)
        location = response.headers.get("location")
        if not location:
            return response, str(response.url)
        current = _safe_redirect(current, location)
    return None, current


async def _bounded_get(client, url: str, timeout: float, started: float, limit: int, range_request: bool = False):
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        remaining = _remaining(timeout, started)
        if remaining <= 0:
            return None, b"", False
        headers = {"Range": f"bytes=0-{limit - 1}"} if range_request else {}
        async with client.stream("GET", current, headers=headers, timeout=max(0.1, remaining)) as response:
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    return response, b"", False
                current = _safe_redirect(current, location)
                continue
            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                if not chunk:
                    continue
                remaining_bytes = limit - size
                chunks.append(chunk[:remaining_bytes])
                size += min(len(chunk), remaining_bytes)
                if size >= limit:
                    break
            return response, b"".join(chunks), size >= limit
    return None, b"", False


def _safe_redirect(current: str, location: str) -> str:
    target = urljoin(current, location)
    parsed = urlsplit(target)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("redirect leaves HTTP(S)")
    return target


def _remaining(timeout: float, started: float) -> float:
    return max(0.0, timeout - (time.monotonic() - started))
