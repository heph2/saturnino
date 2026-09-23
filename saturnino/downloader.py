from __future__ import annotations

import asyncio
import re
import shutil
from collections.abc import Callable
from pathlib import Path

from .models import MediaCandidate
from .utils import DEFAULT_OUTPUT_DIR


class DownloadError(RuntimeError):
    pass


def safe_filename(title: str, episode: str, extension: str) -> str:
    clean_title = re.sub(r"[\\/:*?\"<>|]", "_", title).strip(" .") or "anime"
    clean_episode = re.sub(r"[\\/:*?\"<>|]", "_", episode).strip(" .") or "episode"
    if clean_episode.isdigit():
        clean_episode = clean_episode.zfill(2)
    return f"{clean_title} - {clean_episode}.{extension.lstrip('.') or 'bin'}"


async def download_candidate(
    candidate: MediaCandidate,
    title: str,
    episode: str,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    progress: Callable[[str], None] | None = None,
) -> Path:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    extension = "mp4" if candidate.media_type in {"hls", "dash"} else candidate.media_type
    if extension == "unknown":
        extension = "bin"
    destination = directory / safe_filename(title, episode, extension)
    temporary = destination.with_suffix(destination.suffix + ".part")
    if candidate.media_type in {"hls", "dash"}:
        await _download_with_ffmpeg(candidate.url, temporary, destination)
    else:
        await _download_direct(candidate.url, temporary, destination, progress)
    return destination


async def _download_direct(url: str, temporary: Path, destination: Path, progress: Callable[[str], None] | None) -> None:
    try:
        import httpx
    except ImportError as exc:
        raise DownloadError("httpx is not installed; enter the Nix shell with `nix develop`") from exc
    try:
        async with httpx.AsyncClient(follow_redirects=True, headers={"Accept-Encoding": "identity"}) as client:
            async with client.stream("GET", url, timeout=None) as response:
                if response.status_code < 200 or response.status_code >= 300:
                    raise DownloadError(f"download returned HTTP {response.status_code}")
                total = response.headers.get("content-length")
                total_text = f"/{total} bytes" if total and total.isdigit() else " bytes"
                written = 0
                with temporary.open("wb") as handle:
                    async for chunk in response.aiter_bytes(1024 * 1024):
                        handle.write(chunk)
                        written += len(chunk)
                        if progress:
                            progress(f"Downloaded {written}{total_text}")
        temporary.replace(destination)
    except DownloadError:
        temporary.unlink(missing_ok=True)
        raise
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        raise DownloadError(f"direct download failed: {type(exc).__name__}") from exc


async def _download_with_ffmpeg(url: str, temporary: Path, destination: Path) -> None:
    executable = shutil.which("ffmpeg")
    if not executable:
        raise DownloadError("ffmpeg is required to download HLS/DASH streams")
    process = await asyncio.create_subprocess_exec(
        executable,
        "-y",
        "-i",
        url,
        "-c",
        "copy",
        "-f",
        "mp4",
        str(temporary),
    )
    return_code = await process.wait()
    if return_code != 0:
        temporary.unlink(missing_ok=True)
        raise DownloadError(f"ffmpeg exited with status {return_code}")
    temporary.replace(destination)
