from __future__ import annotations

import math
import re
from pathlib import Path
from urllib.parse import SplitResult, urlsplit, urlunsplit

from .models import EpisodeMetadata

DEFAULT_OUTPUT_DIR = Path.home() / "Downloads" / "saturnino"


def validate_input_url(value: str) -> str | None:
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return "episode URL must be an absolute http(s) URL"
        if parsed.username or parsed.password:
            return "episode URL must not contain credentials"
        parsed.port  # Force malformed ports to raise ValueError.
    except ValueError:
        return "episode URL has an invalid port"
    return None


def validate_timeout(value: str) -> float:
    try:
        timeout = float(value)
    except ValueError as exc:
        raise ValueError("timeout must be a positive finite number") from exc
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be a positive finite number")
    return timeout


def redact_url(value: str) -> str:
    """Remove URL credentials, query values, fragments, and opaque path tokens."""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "<invalid-url>"
    path_parts: list[str] = []
    for part in parsed.path.split("/"):
        if not part:
            path_parts.append(part)
            continue
        if len(part) > 24 or re.search(r"token|secret|sig|expires|key", part, re.I):
            suffix = ""
            match = re.search(r"(\.[A-Za-z0-9]{2,8})$", part)
            if match:
                suffix = match.group(1)
            path_parts.append("[redacted]" + suffix)
        else:
            path_parts.append(part)
    path = "/".join(path_parts)
    query = "[redacted]" if parsed.query else ""
    safe = SplitResult(parsed.scheme, parsed.hostname or "", path, query, "")
    return urlunsplit(safe)


def parse_episode_metadata(url: str, page_title: str | None, heading: str | None) -> EpisodeMetadata:
    text = " ".join(part for part in (heading, page_title) if part)
    episode_match = re.search(r"\b(?:episodio|episode|ep)[\s._-]*(\d+)\b", text, re.I)
    if not episode_match:
        episode_match = re.search(r"/ep[-_/](\d+)(?:$|[/?#])", url, re.I)
    episode = episode_match.group(1) if episode_match else None

    title = heading or page_title
    if title:
        title = re.sub(r"\s*[—|-]\s*(?:episodio|episode|ep)\s*\d+.*$", "", title, flags=re.I)
        title = re.sub(r"\s+(?:streaming|sub\s+ita|ita)\b.*$", "", title, flags=re.I)
        title = title.replace("AnimeSaturn - ", "", 1).strip(" -—") or None
    return EpisodeMetadata(title=title, episode=episode)


def remaining_seconds(deadline: float) -> float:
    import time

    return max(0.0, deadline - time.monotonic())
