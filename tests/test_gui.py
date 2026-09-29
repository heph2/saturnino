import json
from pathlib import Path

import pytest

from saturnino.catalog import EpisodeRef
from saturnino.gui import (
    GuiSettings,
    SaturninoGUI,
    build_player_command,
    carousel_asset_paths,
    default_settings,
    load_settings,
    progress_percent,
    save_settings,
    select_episode_refs,
)


def test_settings_round_trip_persists_only_gui_preferences(tmp_path: Path) -> None:
    path = tmp_path / "gui.json"
    settings = GuiSettings("/media/anime", "/usr/bin/vlc")

    save_settings(settings, path)

    assert load_settings(path) == settings
    assert json.loads(path.read_text()) == {
        "download_dir": "/media/anime",
        "player_executable": "/usr/bin/vlc",
    }


def test_corrupt_settings_fall_back_to_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "gui.json"
    path.write_text("not json")
    monkeypatch.setattr("saturnino.gui.default_settings", lambda: GuiSettings("/default", "mpv"))

    assert load_settings(path) == GuiSettings("/default", "mpv")


def test_episode_selection_preserves_catalog_order() -> None:
    episodes = [EpisodeRef("1", "url-1"), EpisodeRef("2", "url-2"), EpisodeRef("3", "url-3")]

    assert select_episode_refs(episodes, [2, 0]) == [episodes[0], episodes[2]]


def test_player_command_uses_argument_list_without_shell() -> None:
    assert build_player_command("/usr/bin/player", "https://media.test/video.mp4") == [
        "/usr/bin/player",
        "--",
        "https://media.test/video.mp4",
    ]


def test_default_settings_use_existing_download_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("saturnino.gui.DEFAULT_OUTPUT_DIR", tmp_path / "downloads")
    monkeypatch.setattr("saturnino.gui.shutil.which", lambda name: "/usr/bin/mpv" if name == "mpv" else None)

    assert default_settings() == GuiSettings(str(tmp_path / "downloads"), "/usr/bin/mpv")


def test_episode_selection_buttons_select_all_and_clear() -> None:
    class FakeList:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object, object]] = []

        def selection_set(self, first: object, last: object) -> None:
            self.calls.append(("set", first, last))

        def selection_clear(self, first: object, last: object) -> None:
            self.calls.append(("clear", first, last))

    fake = FakeList()
    gui = object.__new__(SaturninoGUI)
    gui.episodes_list = fake

    gui.select_all_episodes()
    gui.clear_episode_selection()

    assert fake.calls == [("set", 0, "end"), ("clear", 0, "end")]


def test_progress_percent_is_bounded_and_handles_unknown_size() -> None:
    assert progress_percent(25, 100) == 25
    assert progress_percent(150, 100) == 100
    assert progress_percent(-1, 100) == 0
    assert progress_percent(25, None) is None
    assert progress_percent(25, 0) is None


def test_theme_palette_is_pink_red_and_white() -> None:
    from saturnino.gui import THEME

    assert THEME["accent"] == "#e94f8a"
    assert THEME["danger"] == "#d9415d"
    assert THEME["surface"] == "#ffffff"


def test_carousel_prefers_transparent_cutouts(tmp_path: Path) -> None:
    (tmp_path / "scene.jpg").touch()
    (tmp_path / "scene_cutout.png").touch()
    (tmp_path / "other_cutout.png").touch()

    assert carousel_asset_paths(tmp_path) == [
        tmp_path / "other_cutout.png",
        tmp_path / "scene_cutout.png",
    ]
