from saturnino.models import RequestObservation
from saturnino.scoring import (
    classify_media_type,
    is_eligible,
    rank_candidates,
    score_observation,
)


def observation(**kwargs) -> RequestObservation:
    values = {
        "request_url": "https://cdn.example/video.m3u8",
        "response_url": "https://cdn.example/video.m3u8",
        "status": 200,
        "content_type": "application/vnd.apple.mpegurl",
        "content_length": None,
        "resource_type": "fetch",
        "frame_id": "frame-1",
        "frame_url": "https://player.example/embed",
        "player_frame": True,
        "interaction_time": 1.0,
        "started_at": 2.0,
        "sequence": 1,
    }
    values.update(kwargs)
    return RequestObservation(**values)


def test_classifies_mime_and_path_without_extension() -> None:
    assert classify_media_type("https://cdn.example/stream", "VIDEO/MP4; codecs=avc1") == "mp4"
    assert classify_media_type("https://cdn.example/manifest", "application/dash+xml") == "dash"
    assert classify_media_type("https://cdn.example/file.M3U8?token=x", None) == "hls"
    assert classify_media_type("https://cdn.example/track?next=movie.mp4", "text/html") == "unknown"


def test_hls_score_contains_independent_reasons() -> None:
    scored = score_observation(observation())
    assert scored.eligible is True
    assert scored.score == 240
    assert "HLS MIME" in " ".join(scored.reasons)
    assert ".m3u8" in " ".join(scored.reasons)


def test_ads_and_segments_cannot_be_selected() -> None:
    ad = observation(
        request_url="https://ads.example/ad.mp4",
        response_url="https://ads.example/ad.mp4",
        content_type="video/mp4",
        frame_id="ad-frame",
        frame_url="https://ads.example/",
        player_frame=False,
        interaction_time=None,
        content_length=20_000_000,
    )
    segment = observation(
        request_url="https://cdn.example/chunk.ts",
        response_url="https://cdn.example/chunk.ts",
        content_type="video/mp2t",
    )
    assert is_eligible(ad) is False
    assert is_eligible(segment) is False


def test_rank_prefers_validated_candidate_over_higher_score_inconclusive() -> None:
    high = observation(sequence=1)
    low = observation(
        request_url="https://cdn.example/video.mp4",
        response_url="https://cdn.example/video.mp4",
        content_type="video/mp4",
        sequence=2,
    )
    candidates = rank_candidates([high, low], validation={
        high.response_url: "inconclusive",
        low.response_url: "valid",
    })
    assert candidates[0].url == low.response_url
