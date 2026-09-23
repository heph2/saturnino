from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .browser import BrowserExtractor, ExtractionError
from .catalog import AnimeCatalog, AnimeResult, CatalogError, EpisodeRef, select_numbers
from .downloader import DownloadError, download_candidate
from .playback import launch_mpv


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


async def _process_episodes(
    anime: AnimeResult,
    episodes: list[EpisodeRef],
    action: str,
    timeout: float,
    headful: bool,
    output_dir: str | Path,
    debug: Callable[[str, dict[str, Any]], None] | None,
    output_fn: Callable[[str], None],
) -> int:
    failure = False
    for episode in episodes:
        output_fn(f"\nExtracting episode {episode.number}...")
        try:
            result = await BrowserExtractor(timeout, headful=headful, debug=debug).extract(episode.url)
            if result.selected is None:
                output_fn(f"Episode {episode.number}: no usable media candidate.")
                failure = True
                continue
            candidate = result.selected
            output_fn(f"Episode {episode.number}: {candidate.media_type.upper()} score {candidate.score}")
            if action in {"p", "play"}:
                if launch_mpv(candidate.url) != 0:
                    failure = True
            else:
                path = await download_candidate(
                    candidate,
                    anime.title,
                    episode.number,
                    output_dir,
                    progress=lambda message: output_fn(f"  {message}"),
                )
                output_fn(f"Saved: {path}")
        except (ExtractionError, DownloadError) as exc:
            output_fn(f"Episode {episode.number} failed: {exc}")
            failure = True
    return 1 if failure else 0
