import asyncio
from pathlib import Path

from saturnino import workflow
from saturnino.catalog import AnimeResult, EpisodeRef
from saturnino.models import ExtractionResult, MediaCandidate


def test_progress_renderer_keeps_one_live_line_per_episode() -> None:
    output: list[str] = []
    progress = workflow._DownloadProgress(
        [EpisodeRef("1", "url-1"), EpisodeRef("2", "url-2")], output.append, interactive=True
    )

    progress.update("1", "downloading", 50, 100)
    progress.update("2", "saved")

    assert "Episode 1" in output[0]
    assert "50%" in output[0]
    assert output[1].startswith("\033[2A")
    assert "Episode 1" in output[1] and "Episode 2" in output[1]


def test_process_episodes_runs_three_end_to_end_jobs_in_parallel(monkeypatch, tmp_path: Path) -> None:
    active = 0
    peak = 0

    class FakeExtractor:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def extract(self, url: str) -> ExtractionResult:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1
            episode = url.rsplit("-", 1)[-1]
            candidate = MediaCandidate(url, "mp4", 100)
            return ExtractionResult("Example", episode, "example.test", candidate, [candidate])

    async def fake_download(candidate, title, episode, output_dir, progress=None):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        if progress:
            progress(50, 100)
        await asyncio.sleep(0.01)
        active -= 1
        path = Path(output_dir) / f"{episode}.mp4"
        path.touch()
        return path

    monkeypatch.setattr(workflow, "BrowserExtractor", FakeExtractor)
    monkeypatch.setattr(workflow, "download_candidate", fake_download)
    output: list[str] = []
    episodes = [EpisodeRef(str(number), f"https://example.test/ep-{number}") for number in range(1, 7)]

    result = asyncio.run(
        workflow._process_episodes(
            AnimeResult("Example", "https://example.test/anime/example"),
            episodes,
            "download",
            45,
            False,
            tmp_path,
            None,
            output.append,
            progress_interactive=False,
        )
    )

    assert result == 0
    assert peak == 3
    assert any("Episode 1" in line and "50%" in line for line in output)
    assert any("Episode 6" in line and "saved" in line for line in output)
