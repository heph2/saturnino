from __future__ import annotations

import re
import time
from collections.abc import Iterable
from typing import Any

PLAY_RE = re.compile(r"^(?:play|guarda|avvia)(?:\b|\s)", re.I)
COOKIE_RE = re.compile(r"cookie|consent|privacy|tracking", re.I)
DISMISS_RE = re.compile(r"^(?:reject|rifiuta|decline|close|chiudi|deny|nega)(?:\b|\s)", re.I)


class PlayerInteractor:
    def __init__(self, interceptor: Any, debug: Any = None) -> None:
        self.interceptor = interceptor
        self.debug = debug
        self._attempted: set[tuple[int, int]] = set()

    async def discover_and_interact(self, pages: Iterable[Any], deadline: float) -> int:
        import asyncio
        interactions = 0
        while time.monotonic() < deadline:
            for page in list(pages):
                await self._dismiss_overlay(page, deadline)
                for frame in list(page.frames):
                    if time.monotonic() >= deadline:
                        break
                    try:
                        evidence, clicked = await self._inspect_frame(frame, deadline)
                    except Exception as exc:
                        self._log("frame_inspection_failed", frame_url=self._safe_url(frame), error=type(exc).__name__)
                        continue
                    if evidence:
                        self.interceptor.mark_player_frame(frame)
                    if clicked:
                        interactions += clicked
            await asyncio.sleep(min(0.5, max(0.0, deadline - time.monotonic())))
            if interactions:
                # Allow one short rescan for requests triggered asynchronously by the click.
                await asyncio.sleep(min(0.5, max(0.0, deadline - time.monotonic())))
                break
        return interactions

    async def _inspect_frame(self, frame: Any, deadline: float) -> tuple[bool, int]:
        import time

        frame_key = id(frame)
        frame_url = self._safe_url(frame)
        evidence = bool(re.search(r"/(?:embed|player|video)(?:/|$)", frame_url, re.I))
        clicked = 0
        if evidence:
            self.interceptor.mark_player_frame(frame)
            self._log("player_frame", frame_url=frame_url)
        videos = frame.locator("video")
        try:
            video_count = await videos.count()
        except Exception:
            video_count = 0
        if video_count:
            evidence = True
            for index in range(min(video_count, 3)):
                video = videos.nth(index)
                try:
                    source = await video.evaluate(
                        """video => ({src: video.currentSrc || video.src || '', paused: video.paused,
                        muted: video.muted, readyState: video.readyState})"""
                    )
                    source_url = source.get("src", "")
                    self._log("video_found", frame_url=self._safe_url(frame), source=source_url)
                    if source_url:
                        self.interceptor.add_dom_media(source_url, frame)
                    if source.get("paused") and time.monotonic() < deadline:
                        self.interceptor.mark_interaction(frame)
                        await video.evaluate(
                            """video => { video.muted = true; const result = video.play();
                            return result && result.catch ? result.catch(() => false) : true; }"""
                        )
                        clicked += 1
                except Exception as exc:
                    self._log("video_play_failed", frame_url=self._safe_url(frame), error=type(exc).__name__)

        if not evidence:
            return evidence, clicked

        buttons = frame.locator("button")
        try:
            count = await buttons.count()
        except Exception:
            count = 0
        for index in range(min(count, 30)):
            if time.monotonic() >= deadline:
                break
            button = buttons.nth(index)
            try:
                if not await button.is_visible():
                    continue
                label = " ".join(
                    part for part in (
                        await button.get_attribute("aria-label"),
                        await button.get_attribute("title"),
                        await button.text_content(),
                    ) if part
                ).strip()
                if not PLAY_RE.search(label):
                    continue
                key = (frame_key, index)
                if key in self._attempted:
                    continue
                self._attempted.add(key)
                evidence = True
                self.interceptor.mark_interaction(frame)
                self._log("player_click", frame_url=self._safe_url(frame), label=label[:80])
                await button.click(timeout=max(100, int((deadline - time.monotonic()) * 1000)))
                clicked += 1
                break
            except Exception as exc:
                self._log("player_click_failed", frame_url=self._safe_url(frame), error=type(exc).__name__)
        return evidence, clicked

    async def _dismiss_overlay(self, page: Any, deadline: float) -> None:
        try:
            dialogs = page.locator('[role="dialog"]')
            for index in range(min(await dialogs.count(), 5)):
                dialog = dialogs.nth(index)
                if not await dialog.is_visible():
                    continue
                text = (await dialog.text_content() or "")[:1000]
                if not COOKIE_RE.search(text):
                    continue
                buttons = dialog.locator("button")
                for button_index in range(min(await buttons.count(), 10)):
                    button = buttons.nth(button_index)
                    label = " ".join(
                        part for part in (
                            await button.get_attribute("aria-label"),
                            await button.get_attribute("title"),
                            await button.text_content(),
                        ) if part
                    ).strip()
                    if DISMISS_RE.search(label) and await button.is_visible():
                        self._log("cookie_overlay_dismiss", label=label[:80])
                        await button.click(timeout=max(100, int((deadline - time.monotonic()) * 1000)))
                        return
        except Exception as exc:
            self._log("overlay_inspection_failed", error=type(exc).__name__)

    @staticmethod
    def _safe_url(frame: Any) -> str:
        try:
            return frame.url
        except Exception:
            return "<detached>"

    def _log(self, event: str, **fields: Any) -> None:
        if self.debug:
            self.debug(event, fields)
