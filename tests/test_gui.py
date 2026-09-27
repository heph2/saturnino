import asyncio
import queue
from pathlib import Path

from saturnino import gui
from saturnino.catalog import EpisodeRef
from saturnino.models import ExtractionResult, MediaCandidate


def test_progress_percent_is_bounded_and_handles_unknown_size() -> None:
    assert gui.progress_percent(25, 100) == 25
    assert gui.progress_percent(150, 100) == 100
    assert gui.progress_percent(-1, 100) == 0
    assert gui.progress_percent(25, None) is None
    assert gui.progress_percent(25, 0) is None


def test_gui_download_can_send_completed_file_to_jellyfin(monkeypatch, tmp_path: Path) -> None:
    uploaded: list[tuple[Path, str, str]] = []

    class FakeExtractor:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def extract(self, _url: str) -> ExtractionResult:
            candidate = MediaCandidate("https://example.test/video.mp4", "mp4", 100)
            return ExtractionResult("Example", "1", "example.test", candidate, [candidate])

    async def fake_download(candidate, title, episode, output_dir, progress=None):
        path = Path(output_dir) / "Example - 01.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"episode")
        return path

    async def fake_upload(path, title, episode, **_kwargs):
        uploaded.append((path, title, episode))
        return "/media/jelly/anime/example/Example_Ep_01_SUB_ITA.mp4"

    monkeypatch.setattr(gui, "BrowserExtractor", FakeExtractor)
    monkeypatch.setattr(gui, "download_candidate", fake_download)
    monkeypatch.setattr(gui, "upload_to_jellyfin", fake_upload)

    app = gui.SaturninoGUI.__new__(gui.SaturninoGUI)
    app.timeout = 45
    app.headful = False
    app._queue = queue.Queue()
    result = asyncio.run(
        app._process(
            [EpisodeRef("1", "https://example.test/ep-1")],
            "download",
            gui.GuiSettings(str(tmp_path), "mpv"),
            "Example",
            send_to_jellyfin=True,
        )
    )

    assert result == ["Episode 1: sent to /media/jelly/anime/example/Example_Ep_01_SUB_ITA.mp4"]
    assert uploaded == [(tmp_path / "Example - 01.mp4", "Example", "1")]
