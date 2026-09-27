import asyncio
from pathlib import Path

import pytest

from saturnino.transfer import TransferError, jellyfin_destination, upload_to_jellyfin


def test_jellyfin_destination_matches_existing_anime_layout() -> None:
    assert jellyfin_destination("Chainsmoker Cat", "1", "mp4") == (
        "chainsmoker_cat",
        "ChainsmokerCat_Ep_01_SUB_ITA.mp4",
    )


def test_jellyfin_destination_sanitizes_folder_and_filename() -> None:
    assert jellyfin_destination("A/B: C?", "special", "mkv") == (
        "a_b_c",
        "ABC_Ep_special_SUB_ITA.mkv",
    )


def test_upload_to_jellyfin_transfers_part_then_atomically_renames(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "episode.mp4"
    source.write_bytes(b"episode")
    commands: list[tuple[str, ...]] = []

    class Completed:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"", b""

    async def fake_exec(*args: str, **kwargs: object) -> Completed:
        commands.append(args)
        return Completed()

    monkeypatch.setattr("saturnino.transfer.asyncio.create_subprocess_exec", fake_exec)

    destination = asyncio.run(
        upload_to_jellyfin(source, "Chainsmoker Cat", "1", host="sauron", root="/media/jelly/anime")
    )

    assert destination == "/media/jelly/anime/chainsmoker_cat/ChainsmokerCat_Ep_01_SUB_ITA.mp4"
    assert commands == [
        ("ssh", "sauron", "mkdir -p -- /media/jelly/anime/chainsmoker_cat"),
        (
            "scp",
            str(source),
            "sauron:/media/jelly/anime/chainsmoker_cat/.ChainsmokerCat_Ep_01_SUB_ITA.mp4.part",
        ),
        (
            "ssh",
            "sauron",
            "mv -f -- /media/jelly/anime/chainsmoker_cat/.ChainsmokerCat_Ep_01_SUB_ITA.mp4.part /media/jelly/anime/chainsmoker_cat/ChainsmokerCat_Ep_01_SUB_ITA.mp4",
        ),
    ]


def test_upload_to_jellyfin_rejects_missing_source(tmp_path: Path) -> None:
    with pytest.raises(TransferError, match="source file does not exist"):
        asyncio.run(upload_to_jellyfin(tmp_path / "missing.mp4", "Example", "1"))
