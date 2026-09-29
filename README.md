<p align="center">
  <img src="assets/the_son_of_saturn.png" alt="Saturnino logo" width="320">
</p>

<h1 align="center">Saturnino</h1>

A local Python CLI that searches AnimeSaturn by title, lets you choose an anime and episodes, extracts fresh playable media URLs with Playwright/Chromium, then either launches mpv or downloads selected episodes. It does not bypass DRM, authentication, CAPTCHA, or access controls.

## Install with Nix

The recommended workflow is a reproducible flake shell containing Python, Playwright, Chromium, ffmpeg, mpv, pytest, Ruff, and mypy:

```bash
nix develop
```

For a one-off command:

```bash
nix develop --command python main.py "Chainsmoker Cat"
```

The shell sets `CHROMIUM_EXECUTABLE_PATH` to the Nix-provided Chromium binary. `flake.lock` pins the nixpkgs revision.

Fallback virtualenv installation:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
playwright install chromium
```

Run checks:

```bash
python -m pytest
python -m ruff check .
python -m mypy saturnino main.py
```

## Usage

Tkinter GUI:

```bash
python -m saturnino.gui
```

The GUI mirrors the title-first workflow: search, choose an anime, select episodes, then play or download. It uses a pink/red/white Saturnino theme and gently cycles through compatible local artwork in `assets/` when available. Transparent `*_cutout.png` artwork is preferred so images can float over themed panels; JPEG artwork uses Pillow, and the GUI falls back to its built-in theme when optional artwork is unavailable. It keeps work off the window thread and lets you change the download folder and URL-capable player executable. Those two GUI preferences are remembered locally; CLI defaults remain unchanged. It also provides a **Send completed downloads to Jellyfin (sauron)** checkbox; enabled downloads are staged locally and uploaded atomically to `sauron:/media/jelly/anime`. Tkinter, Pillow, and a working display are required for the full GUI, so use the CLI on headless systems.

Title-first interactive workflow:

```bash
python main.py "Chainsmoker Cat"
```

The CLI searches AnimeSaturn, lets you choose the anime variant, lists its available episodes, accepts selections such as `1,3-5` or `all`, asks for confirmation, and then offers:

- `p` — extract and launch each selected episode with mpv
- `d` — extract and save each selected episode under `$HOME/Downloads/saturnino/` (or `--output-dir`); up to three episodes run in parallel with one live progress bar per episode

Examples:

```bash
python main.py "Chainsmoker Cat" --output-dir ~/Videos/anime
python main.py "Chainsmoker Cat" --send-to-jellyfin
python main.py "Chainsmoker Cat" --headful --debug
```

Direct episode URLs remain supported:

```bash
python main.py "<episode_url>"
python main.py "<episode_url>" --play
python main.py "<episode_url>" --json
python main.py "<episode_url>" --headful --debug
python main.py "<episode_url>" --timeout 60
```

`--timeout` is a total extraction budget, including navigation, interaction, and validation. `--json` writes one JSON document to stdout; diagnostics and mpv output go to stderr. `--play` extracts immediately before launching `mpv`; if mpv is absent, the URL is still printed normally.

URLs can be signed and expire. They are intentionally printed as the result, so treat stdout as sensitive and do not persist or share it. Debug logs redact query values and opaque path tokens and never print cookies or authorization headers. Playback may still require browser-context cookies or referrers; the tool reports validation limitations rather than exporting credentials.

## Current scope

The generic network observer monitors requests and responses from the start of navigation, including nested frames and popup pages. Candidates are scored using MIME, URL, frame, interaction, size, ad, and resource evidence. HLS, DASH, MP4, WebM, Matroska, and extensionless MIME-qualified media are supported. Validation is bounded and does not download a full video.

Provider-specific behavior is intentionally isolated and generic observation remains the fallback. The title workflow targets AnimeSaturn's observed search/filter and series episode-link structure, then normalizes its verified `/episode/.../ep-N` catalog links to the playable `/anime/.../ep-N` route. Direct URLs remain supported. Direct MP4 downloads use streamed HTTP; HLS/DASH downloads use ffmpeg. Title downloads process up to three episodes concurrently and show per-episode terminal progress bars when stdout is interactive. Downloads default to `$HOME/Downloads/saturnino/`. `--send-to-jellyfin` downloads locally first, then uploads completed files over SSH to `sauron:/media/jelly/anime`, using the existing layout such as `chainsmoker_cat/ChainsmokerCat_Ep_06_SUB_ITA.mp4`. Uploads use a temporary remote `.part` file and an atomic rename; the local staging file is retained. This flag is currently available for title searches, not direct episode URLs. Signed URLs are extracted immediately and not persisted. Results can still vary when the source is unavailable or expired, so use `--headful --debug` for diagnosis.

## Agent skill

A portable harness skill for Codex, Claude Code, and Pi lives in `skills/saturnino-download/`. Install it project-locally with:

```bash
./skills/saturnino-download/install.sh --target all --scope project
```

See its README for user-wide installation paths and the agent workflow for authorized downloads.

## Troubleshooting

- `missing_playwright`: install the Python requirements and run `playwright install chromium`.
- `browser_start`: install Chromium and required system libraries.
- `no_media`: use `--headful --debug` to inspect blocked overlays/player startup and ensure the current page is accessible.
- `no_valid_media`: a candidate was seen but validation rejected or could not independently access it. Signed URLs may have expired or may require browser context.
- `ffmpeg is required`: use the provided Nix shell for HLS/DASH downloads.
- If a site uses DRM, this tool does not attempt to decrypt or bypass it.
