# Saturnino

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

Title-first interactive workflow:

```bash
python main.py "Chainsmoker Cat"
```

The CLI searches AnimeSaturn, lets you choose the anime variant, lists its available episodes, accepts selections such as `1,3-5` or `all`, asks for confirmation, and then offers:

- `p` — extract and launch each selected episode with mpv
- `d` — extract and save each selected episode under `$HOME/Downloads/saturnino/` (or `--output-dir`)

Examples:

```bash
python main.py "Chainsmoker Cat" --output-dir ~/Videos/anime
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

Provider-specific behavior is intentionally isolated and generic observation remains the fallback. The title workflow targets AnimeSaturn's observed search/filter and series episode-link structure, then normalizes its verified `/episode/.../ep-N` catalog links to the playable `/anime/.../ep-N` route. Direct URLs remain supported. Direct MP4 downloads use streamed HTTP; HLS/DASH downloads use ffmpeg. Downloads default to `$HOME/Downloads/saturnino/`. Signed URLs are extracted immediately and not persisted. Results can still vary when the source is unavailable or expired, so use `--headful --debug` for diagnosis.

## Troubleshooting

- `missing_playwright`: install the Python requirements and run `playwright install chromium`.
- `browser_start`: install Chromium and required system libraries.
- `no_media`: use `--headful --debug` to inspect blocked overlays/player startup and ensure the current page is accessible.
- `no_valid_media`: a candidate was seen but validation rejected or could not independently access it. Signed URLs may have expired or may require browser context.
- `ffmpeg is required`: use the provided Nix shell for HLS/DASH downloads.
- If a site uses DRM, this tool does not attempt to decrypt or bypass it.
