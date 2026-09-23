from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
from collections.abc import Sequence
from typing import Any

from .browser import BrowserExtractor, ExtractionError
from .utils import DEFAULT_OUTPUT_DIR, redact_url, validate_input_url, validate_timeout


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract a playable media URL from an episode page")
    parser.add_argument("episode_url", help="episode URL or anime title to search")
    parser.add_argument("--play", action="store_true", help="launch the selected URL with mpv")
    parser.add_argument("--json", action="store_true", help="emit one JSON result")
    parser.add_argument("--headful", action="store_true", help="show Chromium")
    parser.add_argument("--timeout", type=_timeout_arg, default=45.0, help="total timeout in seconds (default: 45)")
    parser.add_argument("--debug", action="store_true", help="write structured diagnostics to stderr")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"download directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    return parser


def _timeout_arg(value: str) -> float:
    try:
        return validate_timeout(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _debug_event(event: str, fields: dict[str, Any]) -> None:
    safe = {key: _sanitize(value) for key, value in fields.items()}
    parts = [f"event={event}"] + [f"{key}={value!r}" for key, value in sorted(safe.items())]
    print(" ".join(parts), file=sys.stderr)


def _sanitize(value: Any) -> Any:
    if isinstance(value, str) and (value.startswith(("http://", "https://")) or "?" in value):
        return redact_url(value)
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, dict):
        return {key: _sanitize(item) for key, item in value.items()}
    return value


def _error_payload(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


def _print_human(result: dict[str, Any]) -> None:
    print(f"Title: {result.get('title') or 'Unknown'}")
    print(f"Episode: {result.get('episode') or 'Unknown'}")
    print(f"Provider: {result.get('provider') or 'Unknown'}")
    print(f"Type: {(result.get('media_type') or 'unknown').upper()}")
    print(f"Confidence: {result.get('score')}")
    print("Media URL:")
    print(result.get("url") or "")
    for warning in result.get("warnings", []):
        print(f"Warning: {warning}", file=sys.stderr)


def _launch_mpv(url: str) -> int:
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


async def _extract(args: argparse.Namespace):
    debug = _debug_event if args.debug else None
    extractor = BrowserExtractor(args.timeout, headful=args.headful, debug=debug)
    return await extractor.extract(args.episode_url)


def main(argv: Sequence[str] | None = None) -> int:
    raw = list(argv) if argv is not None else sys.argv[1:]
    wants_json = "--json" in raw
    parser = build_parser()
    try:
        args = parser.parse_args(raw)
    except SystemExit as exc:
        if wants_json and exc.code != 0:
            print(json.dumps(_error_payload("usage", "invalid command-line arguments")))
        return exc.code if isinstance(exc.code, int) else 1

    is_url = args.episode_url.startswith(("http://", "https://"))
    if not is_url:
        if args.json:
            print(json.dumps(_error_payload("input", "title workflow is interactive; omit --json")))
            return 2
        try:
            from .workflow import run_title_workflow

            return asyncio.run(
                run_title_workflow(
                    args.episode_url,
                    timeout=args.timeout,
                    headful=args.headful,
                    output_dir=args.output_dir,
                    debug=_debug_event if args.debug else None,
                    preferred_action="play" if args.play else None,
                )
            )
        except KeyboardInterrupt:
            print("Error: operation interrupted", file=sys.stderr)
            return 130

    error = validate_input_url(args.episode_url)
    if error:
        payload = _error_payload("input", error)
        if args.json:
            print(json.dumps(payload))
        else:
            print(f"Error: {error}", file=sys.stderr)
        return 2

    try:
        result = asyncio.run(_extract(args))
        payload = result.to_dict()
        play_code = _launch_mpv(payload["url"]) if args.play and payload.get("url") else 0
        if args.json:
            payload["playback_exit_code"] = play_code if args.play else None
            print(json.dumps(payload, ensure_ascii=False))
        else:
            _print_human(payload)
        return play_code
    except KeyboardInterrupt:
        payload = _error_payload("interrupted", "operation interrupted")
        if args.json:
            print(json.dumps(payload))
        else:
            print("Error: operation interrupted", file=sys.stderr)
        return 130
    except ExtractionError as exc:
        payload = _error_payload(exc.code, str(exc))
        if args.json:
            print(json.dumps(payload))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        payload = _error_payload("internal", f"unexpected {type(exc).__name__}")
        if args.json:
            print(json.dumps(payload))
        else:
            print(f"Error: unexpected {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
