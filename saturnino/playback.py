from __future__ import annotations

import shutil
import subprocess
import sys


def launch_mpv(url: str) -> int:
    executable = shutil.which("mpv")
    if not executable:
        print("Warning: mpv is not installed; URL was extracted but not launched.", file=sys.stderr)
        return 0
    try:
        completed = subprocess.run([executable, "--", url], stdout=sys.stderr, stderr=sys.stderr, check=False)
    except OSError as exc:
        print(f"Warning: could not launch mpv: {exc}", file=sys.stderr)
        return 3
    return 0 if completed.returncode == 0 else 3
