# Saturnino — implementation handoff

## 1. Deliverable and current status

Build a local Python CLI that opens an episode with Playwright/Chromium, starts its player where possible, observes browser traffic, ranks media candidates, validates the best candidates, and returns a playable URL. Optionally launch mpv immediately afterward.

**Historical note:** this file was originally produced as a design-only handoff when the repository contained only `.git` and a two-line `README.md`. The implementation now lives under `saturnino/`, with `main.py`, dependencies, and tests. The live acceptance checks in this document remain the source of truth for behavior and caveats; they are not a substitute for the code's test suite.

Implement Phases 1–3 incrementally. Phase 4 (series URL plus episode number) is optional and deferred. Finish and verify Phase 1 before extending it. Preserve generic network extraction even if a provider adapter becomes necessary.

Use only media the operator is authorized to access. Do not implement DRM circumvention, CAPTCHA bypass, authentication bypass, or bulk downloading.

## 2. Supplied live target and observed evidence

Episode URL supplied by the user:

```text
https://www.animesaturn.net/anime/chainsmoker-cat-73cfQ/ep-1
```

Browser inspection performed on 2026-09-23 (environment UTC date):

| Observation | Evidence / implication |
| --- | --- |
| Episode navigation succeeded | Browser network listing reported HTTP 200 for the episode document. |
| Document title | `AnimeSaturn - Chainsmoker Cat Episodio 1 Streaming Sub ITA` |
| Heading | `Chainsmoker Cat — Episodio 1 Streaming Sub ITA e ITA` |
| Player iframe | `iframe#watch-iframe`, title `Chainsmoker Cat Episodio 1`. |
| Observed iframe host/path | `https://play.saturncdn.net/embed/87354`; its actual URL also contained `token` and `expires` query parameters. Values intentionally omitted here. |
| Iframe capabilities | `allow="autoplay; fullscreen; picture-in-picture; encrypted-media"`, `allowfullscreen`, `referrerpolicy="origin"`; no sandbox attribute observed. These do not prove DRM is used. |
| Top-level video | No HTML5 `video` element found on the episode document. |
| Other iframes | A separate `ad.a-ads.com` iframe and empty/hidden iframes were present. Not every iframe is a player. |
| Visible controls in accessibility snapshot | `Cambia player (V)`, `Espandi player`, previous/next episode buttons, and links named `Episodio 1` through `Episodio 11`. Switching providers was not verified. |
| Browser-inspection limitation | Selecting the player frame failed with frame-resolution errors. Clicking the provider-switch control failed with a CDP box-model deserialization error. These are tool failures, not proof the site blocks Playwright. |
| Direct embed inspection | Navigating the same tab to the DOM-observed iframe URL returned an HTTP 200 document titled `Player`; body inspection included `Sorgente non disponibile`. No video or interactive button was found there. |
| Player implementation hints | Embed document referenced `/assets/js/embed/embed.js` and contained JW Player configuration and a Vidstack stylesheet reference. These are hints, not proof of which runtime player successfully initializes. |
| Successful media extraction | **Not verified.** No playable manifest or direct-media response was confirmed. |

Opening an embed as a top-level page changes its execution/referrer context; its failure does **not** establish that normal in-page playback fails. Reinspect with the implementing model's real Playwright Chromium session, preserving the episode/iframe relationship.

Do not copy tokens from inspection logs, hard-code episode ID `87354`, construct private provider endpoints, or implement a decoder based on incidental inline source. Discover current iframe URLs from the current DOM and media URLs from runtime traffic. Never describe this target as supported until the live acceptance test actually succeeds.

After implementation, a fresh local Chromium run against this URL succeeded twice with a newly observed player-frame MP4 and bounded direct-media header validation. The result was not persisted; signed URLs remain transient and future runs may fail if the source is unavailable or expired.

### Required follow-up inspection

1. Attach context-wide request/response listeners before episode navigation.
2. Record the frame tree and inspect the titled iframe through Playwright `Frame` APIs.
3. Inspect visible video elements, open shadow roots, and accessible play controls.
4. Attempt the conservative interaction sequence in section 7.
5. If the source is unavailable, capture a redacted diagnostic and try `--headful`; do not fabricate a result.
6. Only add site/provider-specific selectors after observing them, with a fixture/regression test and an evidence note.

## 3. CLI contract

Required invocation and flags:

```bash
python main.py "<episode_url>"
python main.py "<episode_url>" --play
python main.py "<episode_url>" --json
python main.py "<episode_url>" --headful --debug
python main.py "<episode_url>" --timeout 60
python main.py "Chainsmoker Cat"
python main.py "Chainsmoker Cat" --output-dir "$HOME/Downloads/saturnino"
```

A non-URL positional argument is treated as an anime title. The interactive workflow searches AnimeSaturn, lets the operator choose a result and episode range, confirms the batch, then offers play or download. `--json` remains an episode-URL machine-output mode; title search is intentionally interactive for now. `--output-dir` controls downloaded files and defaults to `$HOME/Downloads/saturnino/`.

- One positional HTTP(S) episode URL; reject missing hosts, URL credentials, unsupported schemes, malformed ports, and invalid timeout values.
- Do not hard-code an AnimeSaturn domain allowlist: domains/providers change, and local fixture URLs must work.
- `--timeout`: positive finite seconds, default **45**, covering browser startup, navigation, discovery, and validation. Playback duration is outside this budget. Use a monotonic deadline; pass remaining time to each operation and reserve time for validation. Cleanup gets a small bounded grace period.
- `--headful`: show Chromium; default headless.
- `--debug`: structured diagnostic events on stderr, with secret-safe URL rendering.
- `--json`: exactly one JSON document on stdout, including failures. Diagnostics and mpv output must not corrupt it.
- `--play`: validate/extract immediately before launching mpv; missing mpv is a warning, not an extraction failure.
- No persistent URL cache, user browser profile, or cookies file by default.
- Treat this as a local operator tool, not an Internet-facing URL-fetching service. A server wrapper would require separate SSRF controls.

### Human-readable success

```text
Title: Chainsmoker Cat
Episode: 1
Provider: play.saturncdn.net
Type: HLS
Confidence: 240
Media URL:
<freshly extracted URL>
```

The format above is illustrative, **not a result from the inspected target**. Confidence is an additive heuristic score, not a probability or percentage. Unknown metadata prints `Unknown`. Report validation limitations on stderr.

### JSON success

Required keys remain compatible with the user's requested shape:

```json
{
  "title": "Chainsmoker Cat",
  "episode": "1",
  "provider": "play.saturncdn.net",
  "media_type": "hls",
  "url": "https://media.example.invalid/master.m3u8",
  "score": 240,
  "validation": "valid",
  "warnings": [],
  "candidates": [
    {
      "url": "https://media.example.invalid/master.m3u8",
      "media_type": "hls",
      "score": 240,
      "reasons": ["+100 HLS MIME", "+90 .m3u8 path", "+30 player frame", "+20 after interaction"],
      "status": 200,
      "content_type": "application/vnd.apple.mpegurl",
      "content_length": null,
      "validation": "valid"
    }
  ]
}
```

Use `null` for unknown JSON metadata. Candidate URLs must remain usable, including necessary signed query strings; this intentional result output is sensitive. Do not include cookies, authorization headers, arbitrary response headers, or full frame URLs in normal JSON.

Suggested exit codes: `0` extraction succeeded; `1` extraction/browser/navigation failure; `2` argparse/input error; `3` mpv launch/playback failure after successful extraction; `130` interrupted. In JSON mode, serialize operational failures as `{"error":{"code":"no_media","message":"..."}}`. Route parser failures through the same JSON convention when `--json` is requested. For `--json --play`, produce a single combined result after mpv exits, with optional playback status; never emit a second JSON document.

## 4. Minimal architecture

Use Python 3.11+ with type hints, dataclasses, `argparse`, `logging`, and `asyncio`. Recommended browser API: `playwright.async_api`. Avoid a framework, database, plugin loader, or parallel extraction service.

```text
saturnino/
    __init__.py
    cli.py                 # Parse args, output, exit mapping, mpv execution
    browser.py             # Context lifecycle, deadline, page/frame coordination
    interceptor.py         # Request/response observation and candidate aggregation
    scoring.py             # Pure classification, scoring, deterministic ranking
    player.py              # Generic discovery and bounded interaction
    validation.py          # Bounded HTTP probes and validation results
    catalog.py             # Title search, series parsing, episode selection
    downloader.py          # Streamed direct downloads and ffmpeg HLS/DASH handoff
    playback.py            # Safe mpv subprocess launch
    workflow.py            # Interactive title-first orchestration
    models.py              # Typed records and result contracts
    utils.py               # URL parsing/redaction; keep small
    providers/
        __init__.py
        base.py            # Only when introducing adapter support in Phase 3
main.py                    # Thin CLI entry point
requirements.txt
requirements-dev.txt
flake.nix
flake.lock
pyproject.toml             # Lint/type/test configuration, if configured
README.md
tests/
    test_scoring.py
    test_classification.py
    test_selection.py
    test_validation.py
    test_cli.py
    test_redaction.py
    integration/
        test_browser.py
        fixtures/
```

Dependencies: the recommended environment is `flake.nix`/`flake.lock` via `nix develop`, providing Python, Playwright, HTTPX, Chromium, ffmpeg, mpv, pytest, Ruff, and mypy. `requirements.txt` and `requirements-dev.txt` remain a fallback for virtualenv users. Keep browser imports out of pure scoring/classification modules. Pin or constrain dependencies to versions actually installed/tested and record the tested Python/Playwright/Chromium versions; do not invent version pins in advance.

### Data model responsibilities

- **RequestObservation**: internal request ID; request URL; response URL when known; method; HTTP status; redirect chain; normalized content type; content length; resource type; page/frame IDs and frame URL snapshot; monotonic start time; interaction association; request failure reason. Missing data is nullable.
- **FrameInfo**: stable session-local ID, parent/page IDs, current URL, observed iframe src/title, navigation history, player evidence. Keep iframe `src` separate from current frame URL.
- **MediaCandidate**: exact usable URL, media type (`hls`, `dash`, `mp4`, `webm`, `mkv`, `unknown`), associated observations, best relevant response metadata, score/reasons, player association, validation state/reason, first-seen time. Mark segments separately so they cannot be selected as complete streams.
- **ValidationResult**: `valid`, `invalid`, or `inconclusive`; reason; checked URL/final URL; HTTP status; checked-at time; safe playback context held in memory only.
- **ExtractionResult**: title, episode, provider, selected candidate, ranked candidates, warnings.

An unavailable metadata field must not crash extraction. Typed strings/enums are sufficient; do not introduce an extensive object hierarchy.

## 5. Browser lifecycle and observation

1. Start the global deadline, launch Chromium, create one isolated nonpersistent context.
2. Register `context.on("request", ...)`, `response`, `requestfailed`, and `page` handlers **before creating/navigating the first page**. Context-wide listeners cover nested frames and new pages, including popup navigation that page-only listeners can miss.
3. For each page, register frame attachment/navigation/detachment, crash/close, and dialog handlers. Dismiss JavaScript dialogs; do not accept arbitrary prompts.
4. Navigate using `wait_until="domcontentloaded"` with a bounded navigation slice. Do not require `networkidle`: streaming and advertising can prevent it forever.
5. Discover/inspect frames, attempt playback, and collect candidates until a settling window or the discovery deadline.
6. Validate ranked candidates while the context remains alive; choose the result and obtain any required in-memory playback context.
7. For `--play`, start playback promptly. Keep the context available through launch if needed; close all owned resources on success, failure, or cancellation.

Network handlers must be fast. Track asynchronous metadata tasks explicitly, surface their failures, and await/cancel them at shutdown; do not leak fire-and-forget tasks. Snapshot request time/frame provenance before later navigations change those values.

### Metadata details

- Observe requests even when they never produce responses. Observe response headers as soon as they arrive, without waiting for video downloads to finish.
- HTTP 404/403/500 are HTTP responses, not necessarily `requestfailed` events. Record status explicitly.
- Follow `Request.redirected_from`/`redirected_to` relationships; each redirect is a separate request. Preserve all hops and final response URL, not just the first URL.
- `request.frame` can be unavailable (including some service-worker/early navigation requests). Handle the documented exception and record unknown provenance rather than discarding traffic.
- Normalize header names and MIME parameters/case. Invalid or absent Content-Length means unknown, not zero or an exception.
- Retain duplicate attempts separately; deduplicate final candidates by exact URL without fragment. Do not strip, decode, sort, or rewrite signed query parameters. A later failed retry must not overwrite a successful observation without retaining both.
- No default blanket ad blocking or script blocking. It can break players. Known ad evidence is useful for ranking and conservative popup dismissal, not permission to discard every new window.
- Do not block service workers by default. If necessary, a documented diagnostic retry with them blocked can test missing visibility, but may break the site and must not silently replace normal behavior.
- Keep candidate/evidence state bounded. Suggested limit: 10,000 metadata observations and 100 candidate URLs; evict oldest irrelevant metadata first, preserve candidate evidence, and warn on truncation.

## 6. Frame traversal and provider handoffs

Use `page.frames` (all attached descendants) or explicit `frame.child_frames` recursion with stable IDs to avoid duplicate work. Inspect each frame's DOM using its own Playwright `Frame`; cross-origin frames cannot be traversed through parent-page JavaScript but can often be inspected by Playwright.

Inspect iframe elements in each frame to capture declared `src`, title, visibility, and parentage. Associate them with child frames where possible. Rescan on new pages/frame navigation and during bounded discovery: dynamically inserted nested frames must not be missed.

Player evidence includes a visible video, accessible player controls, a relevant iframe title, or association with a deliberately activated player. The observed `watch-iframe` selector is a possible site-specific hint, not a universal assumption. Do not award player-frame points to every iframe.

Keep monitoring context-wide traffic if a click opens another page/host. Preserve opener and interaction association. Inspect plausible player pages; close only confidently identified ad popups after recording the decision. Cap active inspected popup pages (suggested 5) and report the cap. On detached/blocked frames, log the scoped failure and continue other frames; never suppress all exceptions with a bare `except`.

## 7. Conservative interaction policy

Try in this order, initially in the main page and then relevant descendant frames:

1. **HTML5 video**: inspect `currentSrc`, `src`, nested `source` elements, ready state, and paused state. Record HTTP(S) DOM URLs as unconfirmed candidates. If paused, attempt `video.play()` and report rejected promises; muting for an autoplay attempt is acceptable. A `blob:` URL is not an external playable URL: retain it only as diagnostic evidence and continue observing manifests/segments.
2. **Visible play control**: inspect accessible roles/names, labels, and native controls. Click a visible play button associated with the player, not a random matching page link.
3. **Localized controls**: conservatively match whole words such as `Play`, `Guarda`, or `Avvia` within the player region. Do not match unrelated episode/download/navigation controls.
4. **Player iframe**: repeat video/control discovery inside the iframe and nested frames; inspect custom elements/open shadow roots through Playwright locators. Do not use screen-coordinate guesses or click arbitrary iframe centers.

Playwright's standard semantic locators are preferred. Any provider-specific selector must be verified on the current DOM. If a custom canvas player exposes no safe actionable control, report the limitation and use a verified adapter or headful/manual interaction rather than inventing selectors.

For overlays, first inspect visible dialogs and known cookie notices; click an explicit close/reject-optional-cookies control when identifiable. Never accept unrelated terms, notifications, purchases, or arbitrary banners. Do not delete every overlay from the DOM.

Use small per-action timeouts bounded by the global deadline. Remember attempted actions per frame/navigation and limit repeated attempts (e.g. two per control). Set interaction time **before** an attempted action so synchronous requests from the click can be attributed; do not grant a global bonus to unrelated ad traffic occurring afterward.

## 8. Classification and scoring

Pure functions should implement MIME normalization, URL classification, eligibility, scoring, and deterministic ranking independently of Playwright.

Classify URL **path**, case-insensitively, excluding query/fragment. `file.M3U8?token=...` is HLS; `/track?next=movie.mp4` is not a direct MP4 merely because the query mentions one. Never assume an extension exists.

Recognize:

- `application/vnd.apple.mpegurl`, `application/x-mpegurl`, and compatible HLS MIME aliases such as `audio/mpegurl` / `audio/x-mpegurl`.
- `application/dash+xml` and `.mpd`.
- `video/*`, including MP4/WebM/Matroska types; known direct extensions `.mp4`, `.webm`, `.mkv`.
- Extensionless `fetch`/XHR responses with recognized media MIME types.
- Manifest-like URL hints as **provisional probe candidates**, not automatic playable URLs. Generic JSON configuration endpoints named `playlist` are not themselves HLS.

Score independent evidence once per category:

| Evidence | Delta |
| --- | ---: |
| `video/*` MIME | +100 |
| HLS MIME (including HLS aliases) | +100 |
| `.m3u8` path | +90 |
| `.mp4` path | +90 |
| DASH MIME or `.mpd` path, once | +80 |
| `.webm` or `.mkv` path | +80 |
| Direct-media full representation length >= 5 MiB | +40 |
| Confirmed player-frame association | +30 |
| Request associated with a player interaction, after its start | +20 |
| Strong tracking/analytics host or endpoint evidence | -100 |
| Image/font/script/stylesheet resource or non-HLS audio MIME | -100 |
| Confidently identified advertising network | -50 |

For partial HTTP 206 responses, Content-Length measures that range, not total size; use a valid Content-Range total for the size bonus. Do not award a size bonus to playlists or arbitrary large downloads. Tracking/ad rules should use host boundaries/explicit evidence, not substrings such as `ad` anywhere in a hostname.

### Eligibility precedes ranking

Scores alone must not allow a large advertisement, HTML error response, or transport segment to win:

- Exclude `blob:`, `data:`, unsupported schemes, known standalone HLS/DASH segments (`.ts`, `.m4s`, initialization fragments), clear image/script/audio-only assets, and definitive failed/error responses from final selection.
- `video/mp2t` and segment URLs with `video/*` must not outrank the manifest that supplies the complete program.
- A filename ending in `.mp4` whose response is HTML is not verified MP4. Probe when evidence conflicts; reject confirmed HTML/JSON error bodies.
- Known advertising media can remain in diagnostics but cannot be selected as the episode solely because it has a high score. Without enough evidence to distinguish an ad from the program, warn or fail honestly.
- MIME-supported media is eligible even with an extensionless URL and `fetch` resource type.
- Positive score without positive media evidence is insufficient.

Keep scores/reasons available for rejected candidates. Sort the public candidate list by descending confidence with deterministic ties (manifest preference, then first-seen sequence). Selection is separate: prefer a validated eligible candidate over an inconclusive one; report why a lower-scoring candidate was selected if necessary.

For the same established HLS presentation, prefer a valid master playlist over its variant: it preserves adaptive quality/audio choices. Do not infer that two arbitrary manifests belong together. Confidence is not resolution; selecting the highest bitrate or rewriting variant URLs is not required.

## 9. Observation window and selection

Do not return the first matching request. Allow delayed manifests, player interactions, and response headers to arrive.

Suggested stopping rule: after a plausible successful media response and at least one player discovery pass, wait a 2-second window without new/updated candidate evidence; otherwise use the discovery deadline. Unrelated analytics requests must not reset this window. This is a bounded heuristic, not proof that no later candidate exists.

Reserve up to 8 seconds (bounded by remaining total time) for validation. Validate highest-scoring eligible candidates first, stopping after a validated best available candidate or a small cap (suggested 5 probes). Honor all remaining deadline limits. Record skipped/unattempted validation explicitly.

If no candidate validates, allow a strongly supported successful browser-observed candidate only when validation is **inconclusive**, with a conspicuous warning and state in JSON. Never fall back to a candidate already known invalid. If no eligible candidate remains, return a useful failure with reasons and `--headful --debug` guidance.

## 10. Lightweight stream validation

Run validation before closing the browser context and immediately before playback. Validation verifies plausible access/content, not a complete episode decode.

### Transport safeguards

- Use `httpx.AsyncClient.stream(...)` with connection/read timeouts and the remaining global deadline. Close responses/clients in `finally`/context managers.
- Never use an ordinary full-body GET to validate a video. A `Range` header is a request, not a guarantee: a server may ignore it and return the entire representation.
- Do not use Playwright `APIRequestContext.get()` followed by `body()[:limit]` as a download bound: response bodies are retained by that API; slicing afterward does not limit transfer. `HEAD` can use a header-only API, but bounded GET must be genuinely streamed.
- Suggested body-read cap: 256 KiB for manifests and 4 KiB for headerless/mislabeled direct-media fallback. Stop reading and close once the application cap is reached. Transport buffers can receive a little more; the invariant is no unbounded/full-video read.
- Use `Accept-Encoding: identity` where possible and enforce limits on actual decoded bytes too.
- Follow at most five redirects explicitly. Resolve relative locations, require HTTP(S), record each hop, and recompute credential scope per destination.

### Browser context and credentials

Use the observed media request's effective Referer/Origin/User-Agent only when needed; the supplied iframe uses origin-only referrer policy, so do not assume the full episode URL is always the correct Referer. Preserve browser cookie domain/path/secure scoping by obtaining applicable cookies for each request URL. Do not blindly forward a Cookie or Authorization header to another host on redirect. Do not export cookies or headers to JSON/debug output.

A separate HTTP client can be blocked even while the browser plays successfully. Distinguish a validation transport/context limitation from a definitively invalid stream; do not claim a public URL is independently playable if it needs browser credentials.

### HLS

1. Stream a bounded GET (optional Range), following the safe redirect policy.
2. Require a successful nonempty response and decoded text starting with `#EXTM3U`, allowing BOM/leading whitespace.
3. Require plausible playlist structure: master entries (`#EXT-X-STREAM-INF`/renditions) or media-playlist evidence such as `#EXTINF`/low-latency HLS parts. A body containing that string in HTML is not enough.
4. If the cap truncates a large playlist, record that full syntax was not checked; do not label a truncated XML/text body definitively corrupt.
5. Never download referenced segments, keys, or the whole video for validation. A valid manifest does not prove segments/keys are accessible or non-DRM.

### DASH

Perform a bounded streamed GET. Verify plausible XML with an `MPD` root (handle namespace) and presentation structure using a safe parser; do not fetch representations or license endpoints. An HTML/XML error document is not DASH. Report encryption indications if observed without claiming decryption capability.

### Direct video

Try HEAD, follow safe redirects, and inspect status/MIME/length. Accept successful plausible video headers; an absent Content-Length is normal. HTTP 204 is not usable media. If HEAD is unsupported (405/501), suspicious, or context-dependent, try a tiny streamed Range GET. Reject confirmed HTML/JSON errors; conservative signature checks may support opaque octet-stream content. Never mistake 403 on HEAD alone for definitive expiry if GET can work.

Statuses 401/403/404/410 from a representative GET indicate denied/unavailable media; report that expiry is a possibility, not a certainty. If time remains and evidence suggests stale signed URLs, allow **one** fresh episode reload/discovery cycle. Use a new candidate generation so old failed URLs are not selected; do not persist or endlessly retry expired URLs.

## 11. Metadata, providers, and playback

### Episode metadata

Prefer the current episode heading/document metadata, then document title, then conservative URL parsing. For the observed target, `Episodio 1` and `/ep-1` agree; `/ep-N` is a verified hint for this example, not a universal site contract. Normalize common site prefixes/suffixes only with tests. Preserve the original page title as a fallback instead of guessing the anime name.

### Provider identity and adapters

Default provider identity is the hostname of the associated player frame (here, potentially `play.saturncdn.net`), not automatically the video CDN or the first third-party iframe. If association is missing, report unknown or an explicitly labeled host fallback. A JW Player script is a player library, not necessarily the hosting provider.

Generic discovery/network observation always runs. In Phase 3, a small protocol is enough if an adapter is needed:

```python
class ProviderExtractor(Protocol):
    def can_handle(self, frame_url: str) -> bool: ...
    async def interact(self, frame: Frame, deadline: float) -> bool: ...
    async def extract(self, frame: Frame, deadline: float) -> list[MediaCandidate]: ...
```

Adapters may provide verified interaction or DOM evidence. Their candidates go through exactly the same scoring/validation path; they cannot bypass eligibility. Adapter failure logs a scoped warning and leaves generic observation working. No adapter is required merely to map a host label, and no provider-specific endpoint is authorized by this document.

### mpv

- Find mpv with `shutil.which("mpv")`.
- Launch using an argument list and no shell, e.g. `subprocess.run([mpv_path, "--", media_url], ...)`.
- Direct child stdout/stderr to stderr so JSON stdout remains parseable. Handle launch failure, nonzero exit, and Ctrl-C; terminate/reap the owned child on interruption.
- Missing mpv: print the normal result, warn, exit successfully.
- If observed Referer/User-Agent is required, use the documented mpv options verified against the installed version. Do not shell-quote an argument list or dump command-line secrets into logs.
- Do not export browser cookies or bearer credentials to files/command arguments by default. Cookie-dependent playback is a documented limitation; return a contextual-playback warning rather than silently claiming mpv will work.
- No persistent cache, background renewal service, or automatic endless playback retry. URLs may expire during playback; rerun extraction for a fresh URL.

## 12. Errors, diagnostics, and privacy

Use structured logging fields such as `event`, `page_id`, `frame_id`, `candidate_id`, `elapsed_ms`, `status`, `score`, and `reason`. A simple key/value formatter is sufficient; another logging dependency is unnecessary.

| Condition | Required behavior |
| --- | --- |
| Missing Playwright/browser binary/system libraries | Explain installation commands and platform dependency needs. |
| Navigation timeout | Warn and inspect any surviving loaded DOM/network evidence within remaining time; fail if unusable. |
| Top-level HTTP error | Include status and safe host context; do not treat a loaded error page as episode success. |
| Page redirect / player popup | Preserve provenance and continue monitoring the same context. |
| Detached/blocked frame | Scoped diagnostic, inspect other frames, no blanket crash. |
| Missing/unavailable player | Distinguish no frame/control from no media observed; suggest headful inspection. |
| Multiple streams | Ranked candidates and deterministic selection with reasons. |
| Expired/denied URL | Validate, optionally refresh once, otherwise return actionable failure. |
| Browser disconnect/crash | Structured error and guaranteed cleanup. |
| Validation inconclusive | Explicit warning/state; never rename it `valid`. |
| Internal unexpected exception | Log sanitized failure, return nonzero, retain enough detail for debugging without leaking credentials. |

`--debug` must include frame navigation/URLs, iframe discovery, interaction attempts/outcomes, candidate detection, score reasoning, validation decisions, and request failures. URL logging is **redacted**: remove userinfo, all query values and fragments; mask token-bearing/opaque path components. Prefer host plus safe path template and an internal ID/hash when sanitization is uncertain. Sanitize exception messages too: Playwright errors can embed full signed URLs. Log only an allowlist of metadata headers (Content-Type/Length/Range); never Cookies, Set-Cookie, Authorization, or request bodies.

Normal result URLs are deliberately usable and may contain access tokens. Explain that redirecting/sharing stdout can disclose temporary media access. Debug logs must not redundantly print those raw URLs.

Raw Playwright traces/HAR files may contain cookies, signed URLs, DOM content, and bodies. **Do not automatically save them under `--debug`.** Trace export is optional future explicit opt-in with a strong warning; no untested promise of automatic sanitization. A sanitized network-metadata export can be added later without bodies/secrets, but is not required for initial implementation.

## 13. Phased implementation and verification

Write failing tests before the corresponding implementation. After each phase run its tests and all configured static/type checks, fix failures, and record commands/results. Do not advance based only on pseudocode or mocked browser success.

### Phase 1 — small working vertical slice

- CLI, URL/timeout checks, Chromium launch/cleanup, deadline handling.
- Context-wide request/response/failure listeners attached before navigation.
- Typed observations and candidates; MIME/path classification; scoring/selection.
- Human and JSON output; safe debug logging.
- Unit tests plus a local browser fixture that emits direct-media and manifest responses.
- Dependency installation instructions and working README.
- Mark output validation `inconclusive`/not attempted until Phase 2 exists; do not claim playback validation.
- Recognize future-phase flags but explicitly reject `--play` until implemented, rather than silently ignoring it.

**Gate:** CLI extracts/ranks controlled fixture candidates, observes an extensionless MIME-qualified response, emits parseable JSON, handles no-media/errors, and unit/lint/type checks pass. Live target may still fail without player interaction; document that honestly.

### Phase 2 — frames, interaction, validation

- Frame tree/provenance/navigation tracking and popup monitoring.
- Safe video/play/localized controls and overlay handling.
- Interaction-aware ranking; settle window; HTTP streaming validation.
- Candidate validity/preference handling, redirected probes, bounded bodies, stale URL refresh.

**Gate:** real Chromium integration tests exercise nested cross-origin frames, click-triggered manifests, popups, ignored Range, and failed/expired media. Repeat live inspection and document only observed outcomes.

### Phase 3 — playback and hardening

- mpv launch/missing/nonzero/interruption handling.
- Provider identity; adapter interface only as needed; generic fallback remains.
- Metadata normalization, robust user errors, redaction regression tests.
- Full README, tested dependency versions, complete CLI examples.

**Gate:** all required tests pass, JSON stays clean under debug/play, process cleanup is verified, and the supplied live URL is tested (or the exact external blocker is reported). Do not claim live compatibility when only fixtures pass.

### Phase 4 — title-first catalog workflow (implemented)

The CLI now accepts a title, searches AnimeSaturn's observed `/filter?key=...` route, presents numbered anime variants, loads the selected series page, parses actual `/episode/.../ep-N` links, accepts episode numbers/ranges/all, confirms the batch, and offers mpv playback or download. It never synthesizes episode URLs. Direct episode URLs remain supported.

The current catalog parser is intentionally scoped to the observed AnimeSaturn DOM and should be extended with fixtures if the site changes. Future work can add JSON/plumbing mode, pagination, specials/non-numeric episode labels, and richer metadata without changing the extractor fallback.

## 14. Test matrix

Most tests must run without launching Chromium; browser integration is a separate opt-in group.

### Pure unit tests

- MIME parameters/case; all required HLS/DASH/video types; HLS audio MIME aliases not penalized as ordinary audio.
- Extensionless media MIME; mixed-case extensions; signed queries/fragments; misleading extensions in query strings; unsupported schemes.
- Exact scoring deltas/reasons; no double-counting; absent/invalid lengths; partial Content-Range; player frame versus ad iframe; per-player interaction association.
- Segment exclusion, HTML pretending to be MP4, known advertising media, failed HTTP responses, blob sources.
- Deterministic ranking; validated lower-score candidate versus invalid/inconclusive higher-score candidate; master/variant preference only with association; no eligible candidates.
- Request/response merging and redirect chains; repeated exact URLs with different statuses; signed URL preservation.
- Metadata parsing for the observed title and unknown/unexpected titles.
- URL/timeout errors, stdout/stderr separation, JSON error schema, mpv argument construction/missing/nonzero cases.
- Secret redaction in URLs, paths, headers, and exception text.

### Validation tests with a local HTTP server

- Valid HLS master/media playlist, BOM, HTML masquerade, wrong MIME with real manifest body, truncated oversized manifest.
- Valid namespace-qualified DASH, invalid/error XML, bounded input.
- HEAD success, 405/501 fallback, HEAD 403 but successful GET, missing length, 206 and Content-Range, 204, GET 401/403/404/410.
- Server ignores Range and attempts a huge/slow response: assert bounded reads and prompt client close, not full-video buffering.
- Redirect loop/hop limit, relative Location, unsupported scheme redirect, cross-host cookie/authorization isolation.
- Deadline/cancellation cleanup, transport errors producing inconclusive results, one refresh at most.

### Real-browser integration fixtures

Serve controlled pages from two localhost origins/ports to exercise genuine cross-origin frames. Use synthetic manifests/tiny media assets only; no copyrighted episode downloads or persisted site tokens.

- Immediate autoplay request proves listeners existed before navigation.
- Nested dynamically inserted frame requests an extensionless HLS URL after a semantic Play button click.
- Localized controls and unrelated `Guarda` links prove clicks remain scoped.
- Blob/MSE-like video surface with underlying manifest request.
- Popup player whose first request is captured by context listeners.
- Ad MP4 arrives before the actual episode manifest; episode wins.
- Frame redirect, detachment, delayed response, page timeout, HTTP error, crash/disconnect simulation.
- Mock provider adapter fails while generic extraction still succeeds.
- Browser context and any child processes are closed after success, error, or interruption.

Tests may use routing/fakes for specific protocol edges, but at least one end-to-end test must use a real local HTTP server and Chromium. Mock-only tests do not prove frame traversal or timing works.

Suggested commands once configured:

```bash
python -m pytest tests/ --ignore=tests/integration
python -m pytest tests/integration
python -m ruff check .
python -m mypy saturnino main.py
```

### Live acceptance

```bash
python main.py "https://www.animesaturn.net/anime/chainsmoker-cat-73cfQ/ep-1" --headful --debug
python main.py "https://www.animesaturn.net/anime/chainsmoker-cat-73cfQ/ep-1" --json
```

Run `--play` when mpv is available and playback is appropriate. Success requires a fresh validated manifest/direct URL associated with the episode, not an advertisement, segment, embed page, or configuration JSON. Record status/type/validation and redacted host/path only in test notes. A transient unavailable source should be reported as such, not hidden by weakening candidate selection.

## 15. README requirements for the implementation

Keep documentation concise but include:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

python main.py "<episode_url>"
python main.py "<episode_url>" --play
python main.py "<episode_url>" --json
python main.py "<episode_url>" --headful --debug
```

Also document timeout semantics, development dependency/test commands, mpv installation being separate, platform-specific Chromium shared-library requirements, expiring/sensitive output URLs, browser-context-dependent playback limitations, DRM/non-goals, troubleshooting, and verified versus unverified live provider support. On unusual Linux environments (including NixOS), report actual browser launch/dependency failures rather than claiming the generic install command always suffices.

## 16. Completion audit for the implementing model

- [ ] Executable Python CLI, not a design-only stub; all five flags behave as documented.
- [ ] Chromium browser lifecycle and deadline are bounded, with useful errors and cleanup.
- [ ] Both requests and responses captured from before navigation, including popups and nested frames.
- [ ] Required metadata, redirects, frame provenance, and resource types recorded.
- [ ] Extensionless media works; segments/ads/error pages do not win.
- [ ] Candidates ranked with transparent deterministic reasons; no first-request shortcut.
- [ ] Conservative interaction; site-specific assumptions backed by actual inspection.
- [ ] Lightweight validation cannot buffer a full video; validity limitations are explicit.
- [ ] Expiry, denied access, missing player, navigation timeout, and browser crashes handled.
- [ ] Fresh extraction before mpv; no shell invocation; missing mpv is graceful.
- [ ] Provider-specific behavior isolated; generic observation survives adapter failures.
- [ ] JSON stdout clean; logs/exports do not dump unnecessary secrets.
- [ ] Unit, validation, real-browser integration, and configured static/type checks pass.
- [ ] README install/usage commands tested or environment blockers stated precisely.
- [ ] Supplied live target tested; actual outcome documented without fabricated compatibility.
- [ ] Optional series discovery remains deferred unless separately requested.

## 17. Documentation references

Consult current docs against the versions actually installed:

- Playwright network observation: https://playwright.dev/python/docs/network
- BrowserContext events/pages: https://playwright.dev/python/docs/api/class-browsercontext
- Request provenance/redirects: https://playwright.dev/python/docs/api/class-request
- Frame APIs: https://playwright.dev/python/docs/api/class-frame
- Locators: https://playwright.dev/python/docs/locators
- APIResponse body retention/disposal: https://playwright.dev/python/docs/api/class-apiresponse
- HTTPX streaming responses: https://www.python-httpx.org/async/#streaming-responses
- mpv options: https://mpv.io/manual/stable/

The network, BrowserContext, Request, and APIResponse documentation was retrieved during design research. Browser observations in section 2 are the only live-site findings claimed by this handoff; proposed implementation behavior elsewhere is not evidence of successful extraction.
