from __future__ import annotations

import asyncio
import re
from pathlib import Path


class TransferError(RuntimeError):
    pass


def jellyfin_destination(title: str, episode: str, extension: str) -> tuple[str, str]:
    folder = re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_").lower() or "anime"
    compact_title = re.sub(r"[^A-Za-z0-9]+", "", title) or "Anime"
    clean_episode = re.sub(r"[^A-Za-z0-9]+", "_", episode).strip("_") or "episode"
    if clean_episode.isdigit():
        clean_episode = clean_episode.zfill(2)
    clean_extension = re.sub(r"[^A-Za-z0-9]+", "", extension).lower() or "bin"
    return folder, f"{compact_title}_Ep_{clean_episode}_SUB_ITA.{clean_extension}"


async def _run(*args: str) -> None:
    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr = await process.communicate()
    except OSError as exc:
        raise TransferError(f"could not run {args[0]}") from exc
    if process.returncode != 0:
        detail = stderr.decode(errors="replace").strip()
        raise TransferError(f"{args[0]} failed{f': {detail}' if detail else ''}")


async def upload_to_jellyfin(
    source: str | Path,
    title: str,
    episode: str,
    *,
    host: str = "sauron",
    root: str = "/media/jelly/anime",
) -> str:
    path = Path(source)
    if not path.is_file():
        raise TransferError(f"source file does not exist: {path}")
    folder, filename = jellyfin_destination(title, episode, path.suffix.lstrip("."))
    remote_dir = f"{root.rstrip('/')}/{folder}"
    remote_path = f"{remote_dir}/{filename}"
    temporary_path = f"{remote_dir}/.{filename}.part"

    await _run("ssh", host, f"mkdir -p -- {remote_dir}")
    try:
        await _run("scp", str(path), f"{host}:{temporary_path}")
        await _run("ssh", host, f"mv -f -- {temporary_path} {remote_path}")
    except TransferError:
        try:
            await _run("ssh", host, f"rm -f -- {temporary_path}")
        except TransferError:
            pass
        raise
    return remote_path
