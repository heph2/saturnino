from __future__ import annotations

import shutil
import subprocess
import sys


def build_player_command(executable: str, url: str) -> list[str]:
    if not executable.strip():
        raise ValueError("player executable is required")
    if not url.strip():
        raise ValueError("media URL is required")
    return [executable, "--", url]


def launch_player(executable: str, url: str) -> int:
    try:
        completed = subprocess.run(build_player_command(executable, url), stdout=sys.stderr, stderr=sys.stderr, check=False)
    except OSError as exc:
        print(f"Warning: could not launch player: {exc}", file=sys.stderr)
        return 3
    return 0 if completed.returncode == 0 else 3


def launch_mpv(url: str) -> int:
    executable = shutil.which("mpv")
    if not executable:
        print("Warning: mpv is not installed; URL was extracted but not launched.", file=sys.stderr)
        return 0
    return launch_player(executable, url)
