---
name: saturnino-download
description: Use Saturnino to search AnimeSaturn, select episodes, and download authorized media locally. Trigger when the user asks to download anime/media with Saturnino, choose episodes, set an output directory, or troubleshoot a Saturnino download.
---

# Saturnino downloads

Use this skill only for media the operator is authorized to access. Saturnino does not bypass DRM, CAPTCHA, authentication, paywalls, or access controls. Do not download or share signed media URLs as a substitute for authorization.

## Before running

1. Locate the Saturnino checkout. Prefer `$SATURNINO_ROOT`; otherwise use the current directory only when it contains `main.py` and `saturnino/`.
2. Ask for the title, episode selection, and destination if any are missing. Do not guess an anime variant or episode range.
3. Prefer the reproducible Nix shell when `flake.nix` is present:

```bash
ROOT="${SATURNINO_ROOT:-$PWD}"
nix develop "$ROOT" --command python "$ROOT/main.py" "TITLE" --output-dir "$DEST"
```

For an activated virtualenv, run from the checkout with `cd "$ROOT" && python main.py ...`. The fallback setup is `pip install -r requirements-dev.txt` followed by `playwright install chromium`; HLS/DASH downloads also need `ffmpeg`.

## Download workflow

The title workflow is the supported download path. It searches, presents variants, lists real episodes, confirms the batch, extracts each episode, and downloads completed files atomically.

```bash
python main.py "TITLE" --output-dir "$HOME/Downloads/saturnino"
```

The command prompts for:

1. anime result number;
2. episodes such as `1,3-5` or `all`;
3. confirmation (`y`);
4. action (`d` / `download`).

With `--send-to-jellyfin`, the action is selected as download automatically, so there is no fourth prompt. In a non-interactive harness, only pipe answers after inspecting the search output and confirming the user's requested selection:

```bash
printf '1\n1,3-5\ny\nd\n' | python main.py "TITLE" --output-dir "$DEST"
```

Use `--headful --debug` when browser/player discovery needs diagnosis. Keep the output directory explicit when the user names one. Up to three episodes are processed concurrently. A completed file is moved into place from a temporary `.part` file.

For the optional Jellyfin transfer, download locally first and then upload completed files:

```bash
python main.py "TITLE" --output-dir "$DEST" --send-to-jellyfin
```

This title-only option targets the configured `sauron:/media/jelly/anime` destination. Do not enable it unless the user asks for that transfer.

## Direct episode URLs

```bash
python main.py "https://example.invalid/anime/show/ep-1"
```

A direct URL extracts and prints a fresh playable URL; it does **not** currently download the file. Do not claim that `--json` or `--play` downloads it. `--json` is for machine-readable extraction results, and `--play` launches `mpv` when available. Use the title workflow for downloads.

Extracting a direct URL as JSON:

```bash
python main.py "$EPISODE_URL" --json
```

Treat the returned URL as sensitive and temporary. Do not persist it in notes, logs, issue comments, shell history, or files unless the user explicitly asks and understands the exposure.

## Agent behavior and failures

- Never silently retry indefinitely. A signed URL can expire; rerun extraction once when useful.
- A missing `Playwright`/Chromium or `ffmpeg` is an environment problem; report the exact install command instead of weakening validation.
- `no_media` or `no_valid_media`: retry with `--headful --debug`, then report the limitation honestly.
- Preserve the CLI's nonzero exit status. Do not report success merely because a `.part` file exists.
- Do not use shell interpolation for media URLs or launch commands. `mpv` must receive an argument list.
- Do not use browser cookies, authorization headers, or private provider endpoints outside the browser context.

## Validation

After a download command finishes, verify the expected destination contains completed files and no unexpected `.part` files. For a single episode, inspect the command exit status and the saved path. Do not open or parse media as proof of content unless the user requests that separately.

Run project checks when changing Saturnino itself:

```bash
nix develop --command python -m pytest
nix develop --command ruff check .
nix develop --command mypy saturnino main.py
```
