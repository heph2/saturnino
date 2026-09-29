import json
from pathlib import Path

import pytest

from saturnino import gui
from saturnino.catalog import EpisodeRef


def test_theme_palette_is_pink_red_and_white() -> None:
    assert gui.THEME["accent"] == "#e94f8a"
    assert gui.THEME["danger"] == "#d9415d"
    assert gui.THEME["surface"] == "#ffffff"


def test_settings_round_trip_persists_only_gui_preferences(tmp_path: Path) -> None:
    path = tmp_path / "gui.json"
    settings = gui.GuiSettings("/media/anime", "/usr/bin/vlc")

    gui.save_settings(settings, path)

    assert gui.load_settings(path) == settings
    assert json.loads(path.read_text()) == {
        "download_dir": "/media/anime",
        "player_executable": "/usr/bin/vlc",
    }


def test_corrupt_settings_fall_back_to_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "gui.json"
    path.write_text("not json")
    monkeypatch.setattr(gui, "default_settings", lambda: gui.GuiSettings("/default", "mpv"))

    assert gui.load_settings(path) == gui.GuiSettings("/default", "mpv")


def test_episode_selection_preserves_catalog_order() -> None:
    episodes = [EpisodeRef("1", "url-1"), EpisodeRef("2", "url-2"), EpisodeRef("3", "url-3")]

    assert gui.select_episode_refs(episodes, [2, 0]) == [episodes[0], episodes[2]]


def test_player_command_uses_argument_list_without_shell() -> None:
    assert gui.build_player_command("/usr/bin/player", "https://media.test/video.mp4") == [
        "/usr/bin/player",
        "--",
        "https://media.test/video.mp4",
    ]


def test_default_settings_use_existing_download_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(gui, "DEFAULT_OUTPUT_DIR", tmp_path / "downloads")
    monkeypatch.setattr(gui.shutil, "which", lambda name: "/usr/bin/mpv" if name == "mpv" else None)

    assert gui.default_settings() == gui.GuiSettings(str(tmp_path / "downloads"), "/usr/bin/mpv")


def test_episode_selection_buttons_select_all_and_clear() -> None:
    class FakeList:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object, object]] = []

        def selection_set(self, first: object, last: object) -> None:
            self.calls.append(("set", first, last))

        def selection_clear(self, first: object, last: object) -> None:
            self.calls.append(("clear", first, last))

    fake = FakeList()
    app = object.__new__(gui.SaturninoGUI)
    app.episodes_list = fake

    app.select_all_episodes()
    app.clear_episode_selection()

    assert fake.calls == [("set", 0, "end"), ("clear", 0, "end")]


def test_progress_percent_is_bounded_and_handles_unknown_size() -> None:
    assert gui.progress_percent(25, 100) == 25
    assert gui.progress_percent(150, 100) == 100
    assert gui.progress_percent(-1, 100) == 0
    assert gui.progress_percent(25, None) is None
    assert gui.progress_percent(25, 0) is None


def test_carousel_prefers_transparent_cutouts(tmp_path: Path) -> None:
    (tmp_path / "scene.jpg").touch()
    (tmp_path / "scene_cutout.png").touch()
    (tmp_path / "other_cutout.png").touch()

    assert gui.carousel_asset_paths(tmp_path) == [
        tmp_path / "other_cutout.png",
        tmp_path / "scene_cutout.png",
    ]


def test_image_fit_preserves_full_aspect_ratio() -> None:
    from saturnino.gui import fit_image_size

    assert fit_image_size(2480, 1754, 700, 240) == (339, 240)
    assert fit_image_size(1529, 2160, 700, 240) == (170, 240)
