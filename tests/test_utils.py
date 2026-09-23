from saturnino.utils import parse_episode_metadata, redact_url, validate_input_url


def test_validate_input_url_rejects_credentials_and_bad_scheme() -> None:
    assert validate_input_url("https://example.com/episode") is None
    assert validate_input_url("ftp://example.com/episode") is not None
    assert validate_input_url("https://user:pass@example.com/episode") is not None
    assert validate_input_url("not-a-url") is not None


def test_redact_url_removes_sensitive_query_values() -> None:
    redacted = redact_url("https://cdn.example/path/token123.m3u8?token=secret&expires=123#x")
    assert redacted == "https://cdn.example/path/[redacted].m3u8?[redacted]"
    assert "secret" not in redacted


def test_parse_episode_metadata_uses_heading_and_title() -> None:
    metadata = parse_episode_metadata(
        "https://www.animesaturn.net/anime/chainsmoker-cat-73cfQ/ep-1",
        "AnimeSaturn - Chainsmoker Cat Episodio 1 Streaming Sub ITA",
        "Chainsmoker Cat — Episodio 1 Streaming Sub ITA e ITA",
    )
    assert metadata.title == "Chainsmoker Cat"
    assert metadata.episode == "1"
