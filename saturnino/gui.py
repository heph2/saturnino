from __future__ import annotations

import asyncio
import json
import os
import queue
import shutil
import sys
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .browser import BrowserExtractor, ExtractionError
from .catalog import AnimeCatalog, AnimeResult, EpisodeRef, select_numbers
from .downloader import download_candidate
from .playback import build_player_command, launch_player
from .utils import DEFAULT_OUTPUT_DIR

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:  # pragma: no cover - depends on the host Python installation.
    tk = None  # type: ignore[assignment]
    filedialog = messagebox = ttk = None  # type: ignore[assignment]


@dataclass(frozen=True, slots=True)
class GuiSettings:
    download_dir: str
    player_executable: str


def default_settings() -> GuiSettings:
    return GuiSettings(str(DEFAULT_OUTPUT_DIR), shutil.which("mpv") or "mpv")


def settings_path() -> Path:
    config_home = os.environ.get("XDG_CONFIG_HOME") or os.environ.get("APPDATA")
    return Path(config_home) / "saturnino" / "gui.json" if config_home else Path.home() / ".config" / "saturnino" / "gui.json"


def load_settings(path: str | Path | None = None) -> GuiSettings:
    defaults = default_settings()
    try:
        data = json.loads(Path(path or settings_path()).read_text())
        if not isinstance(data, dict):
            return defaults
    except (OSError, ValueError, TypeError):
        return defaults
    download_dir = data.get("download_dir")
    player_executable = data.get("player_executable")
    return GuiSettings(
        download_dir if isinstance(download_dir, str) and download_dir else defaults.download_dir,
        player_executable if isinstance(player_executable, str) and player_executable else defaults.player_executable,
    )


def save_settings(settings: GuiSettings, path: str | Path | None = None) -> None:
    destination = Path(path or settings_path())
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps({
        "download_dir": settings.download_dir,
        "player_executable": settings.player_executable,
    }, indent=2) + "\n")
    temporary.replace(destination)


def select_episode_refs(episodes: Sequence[EpisodeRef], indexes: Sequence[int]) -> list[EpisodeRef]:
    wanted = set(indexes)
    return [episode for index, episode in enumerate(episodes) if index in wanted]


def progress_percent(written: int, total: int | None) -> int | None:
    if not total or total <= 0:
        return None
    return max(0, min(100, int(written * 100 / total)))


class SaturninoGUI:
    def __init__(self, root: Any | None = None, *, timeout: float = 45.0, headful: bool = False) -> None:
        if tk is None:
            raise RuntimeError("Tkinter is not available; use the CLI instead")
        self.root = root or tk.Tk()
        self.timeout = timeout
        self.headful = headful
        self.settings = load_settings()
        self.results: list[AnimeResult] = []
        self.episodes: list[EpisodeRef] = []
        self._queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._busy = False
        self._logo: Any | None = None

        self.root.title("Saturnino")
        self.root.geometry("720x560")
        self._build_ui()
        self.root.after(100, self._drain_queue)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _build_ui(self) -> None:
        header = ttk.Frame(self.root, padding=10)
        header.pack(fill="x")
        logo_path = Path(__file__).parent.parent / "assets" / "the_son_of_saturn.png"
        if logo_path.exists():
            try:
                self._logo = tk.PhotoImage(file=str(logo_path))
                scale = max(1, self._logo.width() // 96)
                if scale > 1:
                    self._logo = self._logo.subsample(scale, scale)
                ttk.Label(header, image=self._logo).pack(side="left", padx=(0, 10))
            except tk.TclError:
                self._logo = None
        ttk.Label(header, text="Saturnino", font=("TkDefaultFont", 18, "bold")).pack(side="left")
        self.status_var = tk.StringVar(value="Search for an anime to begin")
        ttk.Label(self.root, textvariable=self.status_var, padding=(10, 0)).pack(fill="x")

        search = ttk.Frame(self.root, padding=10)
        search.pack(fill="x")
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search, textvariable=self.search_var)
        self.search_entry.pack(side="left", fill="x", expand=True)
        self.search_entry.bind("<Return>", lambda _event: self.search())
        self.search_button = ttk.Button(search, text="Search", command=self.search)
        self.search_button.pack(side="left", padx=(8, 0))

        lists = ttk.Frame(self.root, padding=(10, 0))
        lists.pack(fill="both", expand=True)
        ttk.Label(lists, text="Anime results").grid(row=0, column=0, sticky="w")
        ttk.Label(lists, text="Episodes").grid(row=0, column=1, sticky="w")
        self.results_list = tk.Listbox(lists, exportselection=False)
        self.results_list.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        self.episodes_list = tk.Listbox(lists, selectmode="extended", exportselection=False)
        self.episodes_list.grid(row=1, column=1, sticky="nsew")
        lists.rowconfigure(1, weight=1)
        lists.columnconfigure(0, weight=1)
        lists.columnconfigure(1, weight=1)
        ttk.Button(lists, text="Load episodes", command=self.load_episodes).grid(row=2, column=0, pady=8, sticky="w")
        episode_actions = ttk.Frame(lists)
        episode_actions.grid(row=2, column=1, pady=8, sticky="e")
        ttk.Button(episode_actions, text="Select all", command=self.select_all_episodes).pack(side="left")
        ttk.Button(episode_actions, text="Clear", command=self.clear_episode_selection).pack(side="left", padx=(6, 0))

        settings = ttk.LabelFrame(self.root, text="Settings", padding=8)
        settings.pack(fill="x", padx=10, pady=(0, 8))
        self.download_var = tk.StringVar(value=self.settings.download_dir)
        self.player_var = tk.StringVar(value=self.settings.player_executable)
        ttk.Label(settings, text="Download folder").grid(row=0, column=0, sticky="w")
        ttk.Entry(settings, textvariable=self.download_var).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(settings, text="Browse…", command=self.choose_download_dir).grid(row=0, column=2)
        ttk.Label(settings, text="Player executable").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(settings, textvariable=self.player_var).grid(row=1, column=1, sticky="ew", padx=8, pady=(6, 0))
        ttk.Button(settings, text="Browse…", command=self.choose_player).grid(row=1, column=2, pady=(6, 0))
        settings.columnconfigure(1, weight=1)

        actions = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        actions.pack(fill="x")
        self.selection_var = tk.StringVar()
        ttk.Label(actions, text="Selection (optional)").pack(side="left")
        ttk.Entry(actions, textvariable=self.selection_var, width=18).pack(side="left", padx=8)
        self.play_button = ttk.Button(actions, text="Play", command=lambda: self.start("play"))
        self.play_button.pack(side="right")
        self.download_button = ttk.Button(actions, text="Download", command=lambda: self.start("download"))
        self.download_button.pack(side="right", padx=(0, 8))

        progress = ttk.LabelFrame(self.root, text="Progress", padding=8)
        progress.pack(fill="x", padx=10, pady=(0, 8))
        self.progress_var = tk.StringVar(value="Idle")
        ttk.Label(progress, textvariable=self.progress_var).pack(fill="x")
        self.progress_bar = ttk.Progressbar(progress, maximum=100, mode="determinate")
        self.progress_bar.pack(fill="x", pady=(5, 0))

        self.output = tk.Text(self.root, height=5, state="disabled", wrap="word")
        self.output.pack(fill="x", padx=10, pady=(0, 10))

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        for widget in (self.search_button, self.play_button, self.download_button):
            widget.configure(state=state)
        if busy:
            self.progress_bar.configure(mode="indeterminate")
            self.progress_bar.start(12)
            self.progress_var.set("Working…")
        else:
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate")
            if self.progress_var.get() == "Working…":
                self.progress_var.set("Ready")
        self.status_var.set("Working…" if busy else "Ready")

    def _update_download_progress(self, episode: str, written: int, total: int | None) -> None:
        percent = progress_percent(written, total)
        self.progress_var.set(
            f"Episode {episode}: {written:,} bytes" + (f" of {total:,} ({percent}%)" if percent is not None else "")
        )
        if percent is None:
            self.progress_bar.configure(mode="indeterminate")
            self.progress_bar.start(12)
        else:
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate", value=percent)

    def _write(self, text: str) -> None:
        self.output.configure(state="normal")
        self.output.insert("end", text + "\n")
        self.output.see("end")
        self.output.configure(state="disabled")

    def _start_async(self, operation: Callable[[], Any], callback: Callable[[Any], None]) -> None:
        self._set_busy(True)

        def worker() -> None:
            try:
                result = asyncio.run(operation())
            except Exception as exc:  # noqa: BLE001 - surface worker failures in the GUI.
                self._queue.put(("error", exc))
            else:
                self._queue.put(("success", (callback, result)))

        threading.Thread(target=worker, daemon=True).start()

    def _drain_queue(self) -> None:
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "progress":
                    self._write(str(payload))
                elif kind == "download_progress":
                    episode, written, total = payload
                    self._update_download_progress(episode, written, total)
                elif kind == "error":
                    self._set_busy(False)
                    self.status_var.set("Operation failed")
                    self._write(f"Error: {payload}")
                    if messagebox:
                        messagebox.showerror("Saturnino", str(payload), parent=self.root)
                else:
                    callback, result = payload
                    callback(result)
                    self._set_busy(False)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_queue)

    def search(self) -> None:
        title = self.search_var.get().strip()
        if not title or self._busy:
            return
        self._start_async(
            lambda: AnimeCatalog().search(title, min(self.timeout, 20.0), self.headful),
            self._show_results,
        )

    def _show_results(self, results: list[AnimeResult]) -> None:
        self.results = results
        self.results_list.delete(0, "end")
        for result in results:
            label = result.title + (f" — {result.metadata}" if result.metadata else "")
            self.results_list.insert("end", label)
        self.status_var.set(f"Found {len(results)} result(s)")
        self._write("Select an anime, then load its episodes.")

    def load_episodes(self) -> None:
        selected = self.results_list.curselection()
        if not selected or self._busy:
            return
        anime = self.results[selected[0]]
        self._start_async(
            lambda: AnimeCatalog().episodes(anime.url, min(self.timeout, 20.0), self.headful),
            self._show_episodes,
        )

    def _show_episodes(self, episodes: list[EpisodeRef]) -> None:
        self.episodes = episodes
        self.episodes_list.delete(0, "end")
        for episode in episodes:
            self.episodes_list.insert("end", f"Episode {episode.number}")
        self.status_var.set(f"Found {len(episodes)} episode(s)")
        self._write("Select episodes or enter 1,3-5/all, then choose Play or Download.")

    def select_all_episodes(self) -> None:
        self.episodes_list.selection_set(0, "end")

    def clear_episode_selection(self) -> None:
        self.episodes_list.selection_clear(0, "end")

    def choose_download_dir(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.download_var.get()) if filedialog else ""
        if chosen:
            self.download_var.set(chosen)

    def choose_player(self) -> None:
        chosen = filedialog.askopenfilename(initialfile=self.player_var.get()) if filedialog else ""
        if chosen:
            self.player_var.set(chosen)

    def start(self, action: str) -> None:
        if self._busy or not self.episodes:
            return
        expression = self.selection_var.get().strip()
        if expression:
            selected = select_numbers(expression, self.episodes)
        else:
            selected = select_episode_refs(self.episodes, self.episodes_list.curselection())
        if not selected:
            self._write("Choose at least one valid episode.")
            return
        if action == "download" and not self.download_var.get().strip():
            self._write("Choose a download folder.")
            return
        if action == "play" and not self.player_var.get().strip():
            self._write("Choose a player executable.")
            return
        settings = GuiSettings(self.download_var.get().strip(), self.player_var.get().strip())
        selected_anime = self.results_list.curselection()
        anime_title = self.results[selected_anime[0]].title if selected_anime else "Anime"
        self._start_async(
            lambda: self._process(selected, action, settings, anime_title),
            self._show_batch_result,
        )

    async def _process(
        self,
        episodes: list[EpisodeRef],
        action: str,
        settings: GuiSettings,
        anime_title: str,
    ) -> list[str]:
        save_settings(settings)
        messages: list[str] = []
        for episode in episodes:
            self._queue.put(("progress", f"Episode {episode.number}: extracting"))
            result = await BrowserExtractor(self.timeout, headful=self.headful).extract(episode.url)
            if result.selected is None:
                raise ExtractionError("no_media", f"no playable media for episode {episode.number}")
            candidate = result.selected
            if action == "play":
                build_player_command(settings.player_executable, candidate.url)
                code = await asyncio.to_thread(launch_player, settings.player_executable, candidate.url)
                if code:
                    raise ExtractionError("playback", f"player failed for episode {episode.number}")
                messages.append(f"Episode {episode.number}: played")
            else:
                episode_number = episode.number

                def progress(written: int, total: int | None, episode_number: str = episode.number) -> None:
                    detail = f"Episode {episode_number}: downloaded {written} bytes"
                    self._queue.put(("download_progress", (episode_number, written, total)))
                    self._queue.put(("progress", detail + (f"/{total}" if total else "")))

                path = await download_candidate(
                    candidate,
                    anime_title,
                    episode_number,
                    settings.download_dir,
                    progress=progress,
                )
                self._queue.put(("download_progress", (episode_number, 1, 1)))
                messages.append(f"Episode {episode.number}: saved to {path}")
        return messages

    def _show_batch_result(self, messages: list[str]) -> None:
        for message in messages:
            self._write(message)
        self.progress_var.set("Finished")
        self.status_var.set("Finished")

    def close(self) -> None:
        if tk is not None:
            save_settings(GuiSettings(self.download_var.get(), self.player_var.get()))
            self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    if tk is None:
        print("Tkinter is not available; use the CLI instead", file=sys.stderr)
        return 1
    try:
        SaturninoGUI().run()
    except tk.TclError as exc:
        print(f"Could not start the GUI: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
