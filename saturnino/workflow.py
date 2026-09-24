from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .browser import BrowserExtractor, ExtractionError
from .catalog import AnimeCatalog, AnimeResult, CatalogError, EpisodeRef, select_numbers
from .downloader import DownloadError, download_candidate
from .playback import launch_mpv

MAX_PARALLEL_EPISODES = 3


async def run_title_workflow(
    title: str,
    *,
    timeout: float,
    headful: bool,
    output_dir: str | Path,
    debug: Callable[[str, dict[str, Any]], None] | None = None,
    preferred_action: str | None = None,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> int:
    catalog = AnimeCatalog()
    try:
        output_fn(f'Searching AnimeSaturn for "{title}"...')
        results = await catalog.search(title, min(timeout, 20.0), headful)
        if not results:
            output_fn("No anime results found.")
            return 1
        anime = _choose_anime(results, input_fn, output_fn)
        if anime is None:
            return 2
        episodes = await catalog.episodes(anime.url, min(timeout, 20.0), headful)
        if not episodes:
            output_fn("No episodes found for the selected anime.")
            return 1
        selected = _choose_episodes(episodes, input_fn, output_fn)
        if not selected:
            return 2
        confirmation = input_fn(f"Proceed with {len(selected)} episode(s)? [y/N] ").strip().lower()
        if confirmation not in {"y", "yes"}:
            output_fn("Cancelled.")
            return 0
        action = preferred_action or input_fn("Action: [p]lay or [d]ownload? ").strip().lower()
        if action not in {"p", "play", "d", "download"}:
            output_fn("Cancelled.")
            return 0
        return await _process_episodes(anime, selected, action, timeout, headful, output_dir, debug, output_fn)
    except (CatalogError, ExtractionError, DownloadError) as exc:
        output_fn(f"Error: {exc}")
        return 1


def _choose_anime(
    results: list[AnimeResult], input_fn: Callable[[str], str], output_fn: Callable[[str], None]
) -> AnimeResult | None:
    output_fn("\nAnime results:")
    for index, result in enumerate(results, 1):
        suffix = f" — {result.metadata}" if result.metadata else ""
        output_fn(f"  {index}. {result.title}{suffix}")
    try:
        choice = int(input_fn("Choose an anime (number, or q to quit): ").strip())
    except (ValueError, EOFError):
        return None
    return results[choice - 1] if 1 <= choice <= len(results) else None


def _choose_episodes(
    episodes: list[EpisodeRef], input_fn: Callable[[str], str], output_fn: Callable[[str], None]
) -> list[EpisodeRef]:
    output_fn("\nEpisodes:")
    output_fn("  " + "  ".join(episode.number for episode in episodes))
    try:
        value = input_fn("Episodes (e.g. 1,3-5 or all; q to quit): ").strip()
    except EOFError:
        return []
    if value.lower() == "q":
        return []
    selected = select_numbers(value, episodes)
    if not selected:
        output_fn("Invalid episode selection.")
    return selected


class _DownloadProgress:
    def __init__(
        self,
        episodes: list[EpisodeRef],
        output_fn: Callable[[str], None],
        interactive: bool | None,
    ) -> None:
        self._episodes = episodes
        self._output = output_fn
        self._interactive = sys.stdout.isatty() if interactive is None else interactive
        self._lines = {episode.number: f"Episode {episode.number}: queued" for episode in episodes}
        self._rendered = False

    def update(
        self,
        episode: str,
        status: str,
        written: int = 0,
        total: int | None = None,
        detail: str = "",
    ) -> None:
        self._lines[episode] = self._format_line(episode, status, written, total, detail)
        if self._interactive:
            prefix = f"\033[{len(self._episodes)}A" if self._rendered else ""
            body = "\n".join(f"\033[2K{self._lines[item.number]}" for item in self._episodes)
            self._output(prefix + body)
            self._rendered = True
        else:
            self._output(self._lines[episode])

    @staticmethod
    def _format_line(
        episode: str, status: str, written: int, total: int | None, detail: str
    ) -> str:
        width = 20
        if total and total > 0:
            percent = min(100, int(written * 100 / total))
            filled = int(width * percent / 100)
            bar = "#" * filled + "-" * (width - filled)
            progress = f"[{bar}] {percent:3d}% {written}/{total} bytes"
        else:
            progress = "[" + "-" * width + "]      bytes"
        suffix = f" — {detail}" if detail else ""
        return f"Episode {episode}: {status:<11} {progress}{suffix}"


async def _process_episodes(
    anime: AnimeResult,
    episodes: list[EpisodeRef],
    action: str,
    timeout: float,
    headful: bool,
    output_dir: str | Path,
    debug: Callable[[str, dict[str, Any]], None] | None,
    output_fn: Callable[[str], None],
    progress_interactive: bool | None = None,
) -> int:
    progress = _DownloadProgress(episodes, output_fn, progress_interactive)
    semaphore = asyncio.Semaphore(MAX_PARALLEL_EPISODES)

    async def process(episode: EpisodeRef) -> bool:
        async with semaphore:
            progress.update(episode.number, "extracting")
            try:
                result = await BrowserExtractor(timeout, headful=headful, debug=debug).extract(episode.url)
                if result.selected is None:
                    progress.update(episode.number, "failed", detail="no usable media candidate")
                    return True
                candidate = result.selected
                if action in {"p", "play"}:
                    progress.update(
                        episode.number,
                        "playing",
                        detail=f"{candidate.media_type.upper()} score {candidate.score}",
                    )
                    return launch_mpv(candidate.url) != 0
                progress.update(
                    episode.number,
                    "downloading",
                    detail=f"{candidate.media_type.upper()} score {candidate.score}",
                )
                path = await download_candidate(
                    candidate,
                    anime.title,
                    episode.number,
                    output_dir,
                    progress=lambda written, total: progress.update(
                        episode.number, "downloading", written, total
                    ),
                )
                progress.update(episode.number, "saved", 1, 1, str(path))
                return False
            except (ExtractionError, DownloadError) as exc:
                progress.update(episode.number, "failed", detail=str(exc))
                return True

    failures = await asyncio.gather(*(process(episode) for episode in episodes))
    return 1 if any(failures) else 0
