from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlsplit

from .models import MediaCandidate, RequestObservation, ScoreResult

HLS_MIMES = {
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
    "application/mpegurl",
    "audio/mpegurl",
    "audio/x-mpegurl",
}
DASH_MIME = "application/dash+xml"
DIRECT_EXTENSIONS = {".mp4": "mp4", ".webm": "webm", ".mkv": "mkv"}
SEGMENT_EXTENSIONS = {".ts", ".m4s", ".m4v", ".aac", ".cmfv", ".cmfa"}
BAD_RESOURCE_TYPES = {"image", "font", "stylesheet", "script"}


def normalize_content_type(content_type: str | None) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()


def _path_suffix(url: str) -> str:
    try:
        path = urlsplit(url).path.lower()
    except ValueError:
        return ""
    dot = path.rfind(".")
    slash = path.rfind("/")
    return path[dot:] if dot > slash else ""


def classify_media_type(url: str, content_type: str | None) -> str:
    mime = normalize_content_type(content_type)
    suffix = _path_suffix(url)
    if mime in HLS_MIMES or suffix == ".m3u8":
        return "hls"
    if mime == DASH_MIME or suffix == ".mpd":
        return "dash"
    if mime in {"video/mp4", "application/mp4"} or suffix == ".mp4":
        return "mp4"
    if mime in {"video/webm", "audio/webm"} or suffix == ".webm":
        return "webm"
    if mime in {"video/x-matroska", "video/matroska"} or suffix == ".mkv":
        return "mkv"
    if mime.startswith("video/"):
        return "unknown"
    return "unknown"


def _is_ad_url(url: str) -> bool:
    try:
        host = (urlsplit(url).hostname or "").lower()
        path = urlsplit(url).path.lower()
    except ValueError:
        return False
    ad_hosts = ("doubleclick.net", "googlesyndication.com", "a-ads.com", "adnxs.com")
    first_label = host.split(".", 1)[0]
    return (
        host.endswith(ad_hosts)
        or first_label in {"ad", "ads", "advert", "advertising"}
        or any(part in path for part in ("/ads/", "/advert", "/adserver"))
    )


def _is_segment(url: str) -> bool:
    return _path_suffix(url) in SEGMENT_EXTENSIONS


def is_eligible(observation: RequestObservation) -> bool:
    url = observation.final_url
    if not url.startswith(("http://", "https://")):
        return False
    if _is_segment(url):
        return False
    if observation.status is not None and observation.status >= 400:
        return False
    mime = normalize_content_type(observation.content_type)
    if observation.resource_type in BAD_RESOURCE_TYPES:
        return False
    if mime.startswith(("image/", "font/", "text/css", "text/javascript", "application/javascript")):
        return False
    if mime.startswith("audio/") and mime not in HLS_MIMES:
        return False
    if mime in {"text/html", "application/json", "text/plain"} and classify_media_type(url, mime) == "unknown":
        return False
    if _is_ad_url(url):
        return False
    return classify_media_type(url, observation.content_type) != "unknown" or mime.startswith("video/")


def score_observation(observation: RequestObservation) -> ScoreResult:
    url = observation.final_url
    mime = normalize_content_type(observation.content_type)
    suffix = _path_suffix(url)
    media_type = classify_media_type(url, observation.content_type)
    score = 0
    reasons: list[str] = []
    if mime.startswith("video/"):
        score += 100
        reasons.append("+100 video MIME")
    if mime in HLS_MIMES:
        score += 100
        reasons.append("+100 HLS MIME")
    if suffix == ".m3u8":
        score += 90
        reasons.append("+90 .m3u8 path")
    if suffix == ".mp4":
        score += 90
        reasons.append("+90 .mp4 path")
    if mime == DASH_MIME or suffix == ".mpd":
        score += 80
        reasons.append("+80 DASH evidence")
    if suffix in {".webm", ".mkv"}:
        score += 80
        reasons.append("+80 direct-media path")
    size = observation.content_range_total if observation.status == 206 else observation.content_length
    if (
        media_type in {"mp4", "webm", "mkv", "unknown"}
        and size is not None
        and size >= 5 * 1024 * 1024
    ):
        score += 40
        reasons.append("+40 large direct media")
    if observation.player_frame:
        score += 30
        reasons.append("+30 player frame")
    if observation.interaction_time is not None and observation.started_at >= observation.interaction_time:
        score += 20
        reasons.append("+20 after interaction")
    if _is_ad_url(url):
        score -= 50
        reasons.append("-50 advertising evidence")
    if mime.startswith(("image/", "font/", "text/", "application/javascript")) or observation.resource_type in BAD_RESOURCE_TYPES:
        score -= 100
        reasons.append("-100 non-media resource")
    if _is_ad_url(url) and not observation.player_frame:
        score -= 100
        reasons.append("-100 standalone ad")
    return ScoreResult(score=score, reasons=reasons, eligible=is_eligible(observation), media_type=media_type)


def candidate_from_observation(observation: RequestObservation) -> MediaCandidate:
    result = score_observation(observation)
    return MediaCandidate(
        url=observation.final_url,
        media_type=result.media_type,
        score=result.score,
        reasons=result.reasons,
        status=observation.status,
        content_type=observation.content_type,
        content_length=observation.content_length,
        content_range_total=observation.content_range_total,
        resource_type=observation.resource_type,
        frame_id=observation.frame_id,
        frame_url=observation.frame_url,
        player_frame=observation.player_frame,
        sequence=observation.sequence,
        eligible=result.eligible,
    )


def rank_candidates(
    observations: Iterable[RequestObservation],
    validation: dict[str, str] | None = None,
) -> list[MediaCandidate]:
    candidates: dict[str, MediaCandidate] = {}
    for observation in observations:
        if observation.final_url in candidates:
            existing = candidates[observation.final_url]
            fresh = candidate_from_observation(observation)
            if fresh.score > existing.score or (fresh.status and not existing.status):
                candidates[observation.final_url] = fresh
            continue
        candidates[observation.final_url] = candidate_from_observation(observation)
    result = list(candidates.values())
    states = validation or {}
    for candidate in result:
        state = states.get(candidate.url)
        if state:
            from .models import ValidationResult

            candidate.validation = ValidationResult(state, "supplied selection state", candidate.url)
    result.sort(
        key=lambda item: (
            states.get(item.url) == "valid",
            item.eligible,
            item.media_type == "hls",
            item.score,
            -item.sequence,
        ),
        reverse=True,
    )
    return result
