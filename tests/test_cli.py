import json

from saturnino import cli
from saturnino.models import ExtractionResult, MediaCandidate, ValidationResult


def _result() -> ExtractionResult:
    candidate = MediaCandidate(
        url="https://media.example/stream.m3u8?token=secret",
        media_type="hls",
        score=190,
        validation=ValidationResult("valid", "ok"),
    )
    return ExtractionResult("Example", "1", "player.example", candidate, [candidate])


def test_json_output_is_one_document(monkeypatch, capsys) -> None:
    async def fake_extract(_args):
        return _result()

    monkeypatch.setattr(cli, "_extract", fake_extract)
    assert cli.main(["https://example.com/ep-1", "--json"]) == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["url"].endswith("token=secret")
    assert captured.err == ""


def test_invalid_url_has_json_error(monkeypatch, capsys) -> None:
    assert cli.main(["ftp://example.com/ep-1", "--json"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "input"


def test_jellyfin_flag_is_available() -> None:
    args = cli.build_parser().parse_args(["Example", "--send-to-jellyfin"])
    assert args.send_to_jellyfin is True


def test_mpv_uses_argument_list(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(cli.shutil, "which", lambda _name: "/bin/mpv")
    monkeypatch.setattr(cli.subprocess, "run", lambda args, **kwargs: calls.append((args, kwargs)) or type("R", (), {"returncode": 0})())
    assert cli._launch_mpv("https://media.example/video.mp4") == 0
    assert calls[0][0] == ["/bin/mpv", "--", "https://media.example/video.mp4"]
    assert calls[0][1]["check"] is False
