from __future__ import annotations

import asyncio
import os
import shutil
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from .interceptor import NetworkInterceptor
from .models import ExtractionResult, MediaCandidate
from .player import PlayerInteractor
from .scoring import rank_candidates
from .utils import parse_episode_metadata, redact_url, remaining_seconds
from .validation import validate_candidate


class ExtractionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class BrowserExtractor:
    def __init__(self, timeout: float, headful: bool = False, debug: Callable[[str, dict[str, Any]], None] | None = None) -> None:
        self.timeout = timeout
        self.headful = headful
        self.debug = debug
        self.pages: list[Any] = []
        self.page_ids: dict[int, str] = {}
        self._page_counter = 0

    async def extract(self, url: str) -> ExtractionResult:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise ExtractionError("missing_playwright", "Playwright is not installed; run pip install -r requirements.txt") from exc

        deadline = time.monotonic() + self.timeout
        interceptor = NetworkInterceptor(self.debug)
        browser = None
        context = None
        try:
            async with async_playwright() as playwright:
                remaining = remaining_seconds(deadline)
                if remaining <= 0:
                    raise ExtractionError("timeout", "extraction deadline expired before browser launch")
                try:
                    executable_path = os.environ.get("CHROMIUM_EXECUTABLE_PATH") or shutil.which("chromium") or shutil.which("chromium-browser")
                    launch_options: dict[str, Any] = {"headless": not self.headful}
                    if executable_path:
                        launch_options["executable_path"] = executable_path
                    browser = await playwright.chromium.launch(**launch_options)
                    context = await browser.new_context()
                except Exception as exc:
                    raise ExtractionError("browser_start", f"could not launch Chromium: {type(exc).__name__}") from exc

                interceptor.attach(context)
                context.on("page", lambda new_page: self._register_page(new_page, interceptor))
                page = await context.new_page()
                self._register_page(page, interceptor)

                response = None
                try:
                    response = await page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=max(1000, int(min(20.0, remaining_seconds(deadline)) * 1000)),
                    )
                except Exception as exc:
                    self._log("navigation_failed", error=type(exc).__name__, url=redact_url(url))
                    if not self.pages or not page.url:
                        raise ExtractionError("navigation", f"navigation failed: {type(exc).__name__}") from exc
                status = getattr(response, "status", None)
                if status is not None and status >= 400:
                    raise ExtractionError("http_error", f"episode page returned HTTP {status}")

                metadata = await self._metadata(page)
                await self._log_iframes()
                discovery_deadline = time.monotonic() + max(0.5, min(12.0, remaining_seconds(deadline) - 8.0))
                player = PlayerInteractor(interceptor, self.debug)
                await player.discover_and_interact(self.pages, discovery_deadline)
                await self._settle(interceptor, deadline)

                candidates = rank_candidates(interceptor.observations)
                for candidate in candidates:
                    self._log(
                        "candidate_scored",
                        url=redact_url(candidate.url),
                        score=candidate.score,
                        eligible=candidate.eligible,
                        reasons=candidate.reasons,
                    )
                if not candidates:
                    raise ExtractionError("no_media", "no media candidates were observed; try --headful --debug")
                await self._validate_candidates(candidates, deadline)
                selected = self._select(candidates)
                if selected is None:
                    raise ExtractionError("no_valid_media", "media candidates were observed but none were usable")

                provider = self._provider(selected)
                warnings = [
                    f"{candidate.validation.reason}: {redact_url(candidate.url)}"
                    for candidate in candidates
                    if candidate.validation and candidate.validation.state == "invalid"
                ]
                if selected.validation and selected.validation.state == "inconclusive":
                    warnings.append(
                        f"Selected candidate could not be independently validated: {selected.validation.reason}"
                    )
                return ExtractionResult(metadata.title, metadata.episode, provider, selected, candidates, warnings)
        finally:
            if context is not None:
                try:
                    await context.close()
                except Exception as exc:
                    if type(exc).__name__ not in {"TargetClosedError", "Error"}:
                        self._log("context_close_failed", error=type(exc).__name__)
            if browser is not None:
                try:
                    await browser.close()
                except Exception as exc:
                    self._log("browser_close_failed", error=type(exc).__name__)

    def _on_page(self, page: Any) -> None:
        self._register_page(page, None)

    def _register_page(self, page: Any, interceptor: NetworkInterceptor | None) -> None:
        if id(page) in self.page_ids:
            if interceptor:
                interceptor.register_page(page, self.page_ids[id(page)])
            return
        self._page_counter += 1
        page_id = f"page-{self._page_counter}"
        self.page_ids[id(page)] = page_id
        self.pages.append(page)
        if interceptor:
            interceptor.register_page(page, page_id)
        page.on("framenavigated", lambda frame: self._log("frame_navigated", frame_url=redact_url(frame.url)))
        page.on("frameattached", lambda frame: self._log("frame_attached", frame_url=redact_url(frame.url)))
        page.on("framedetached", lambda frame: self._log("frame_detached", frame_url=redact_url(frame.url)))
        page.on("crash", lambda: self._log("page_crashed", page_id=page_id))
        page.on("dialog", lambda dialog: asyncio.create_task(self._dismiss_dialog(dialog)))

    async def _dismiss_dialog(self, dialog: Any) -> None:
        try:
            await dialog.dismiss()
            self._log("dialog_dismissed")
        except Exception as exc:
            self._log("dialog_dismiss_failed", error=type(exc).__name__)

    async def _log_iframes(self) -> None:
        for page in list(self.pages):
            try:
                frames = page.locator("iframe")
                for index in range(min(await frames.count(), 50)):
                    iframe = frames.nth(index)
                    self._log(
                        "iframe_detected",
                        src=redact_url(await iframe.get_attribute("src") or ""),
                        title=(await iframe.get_attribute("title") or "")[:100],
                    )
            except Exception as exc:
                self._log("iframe_inspection_failed", error=type(exc).__name__)

    async def _metadata(self, page: Any):
        try:
            title = await page.title()
        except Exception:
            title = None
        heading = None
        try:
            headings = page.locator("h1")
            if await headings.count():
                heading = await headings.first.text_content()
        except Exception:
            pass
        return parse_episode_metadata(page.url, title, heading)

    async def _settle(self, interceptor: NetworkInterceptor, deadline: float) -> None:
        quiet_until = time.monotonic() + 2.0
        observed = interceptor.version
        while time.monotonic() < deadline and time.monotonic() < quiet_until:
            await asyncio.sleep(0.1)
            if interceptor.version != observed:
                observed = interceptor.version
                quiet_until = time.monotonic() + 2.0

    async def _validate_candidates(self, candidates: list[MediaCandidate], deadline: float) -> None:
        checked = 0
        for candidate in candidates:
            if not candidate.eligible or checked >= 5 or remaining_seconds(deadline) <= 0.5:
                continue
            checked += 1
            result = await validate_candidate(candidate, min(8.0, remaining_seconds(deadline)))
            candidate.validation = result
            self._log("candidate_validated", url=redact_url(candidate.url), state=result.state, reason=result.reason)
            if result.state == "valid":
                break

    @staticmethod
    def _select(candidates: list[MediaCandidate]) -> MediaCandidate | None:
        valid = [item for item in candidates if item.eligible and item.validation and item.validation.state == "valid"]
        if valid:
            return sorted(valid, key=lambda item: (-item.score, item.sequence))[0]
        inconclusive = [item for item in candidates if item.eligible and item.validation and item.validation.state == "inconclusive"]
        if inconclusive:
            return sorted(inconclusive, key=lambda item: (-item.score, item.sequence))[0]
        return None

    @staticmethod
    def _provider(candidate: MediaCandidate) -> str | None:
        try:
            return urlsplit(candidate.frame_url or "").hostname or None
        except ValueError:
            return None

    def _log(self, event: str, fields: dict[str, Any] | None = None, **kwargs: Any) -> None:
        if self.debug:
            values = dict(fields or {})
            values.update(kwargs)
            self.debug(event, values)
