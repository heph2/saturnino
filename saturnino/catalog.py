from __future__ import annotations

import os
import re
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from html.parser import HTMLParser
from time import monotonic
from urllib.parse import quote, urljoin


@dataclass(frozen=True, slots=True)
class AnimeResult:
    title: str
    url: str
    metadata: str = ""


@dataclass(frozen=True, slots=True)
class EpisodeRef:
    number: str
    url: str


class CatalogError(RuntimeError):
    pass


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str, str, str]] = []
        self._current: dict[str, str] | None = None
        self._mode: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a" and self._current is None:
            href = dict(attrs).get("href")
            if href:
                self._current = {"href": href, "text": "", "title": "", "metadata": ""}
        elif self._current is not None and tag in {"h3", "h4"}:
            self._mode = "title"
        elif self._current is not None and tag in {"p", "small"}:
            self._mode = "metadata"

    def handle_data(self, data: str) -> None:
        if self._current is None:
            return
        clean = " ".join(data.split())
        if not clean:
            return
        self._current["text"] += f" {clean}"
        if self._mode == "title":
            self._current["title"] += f" {clean}"
        elif self._mode == "metadata":
            self._current["metadata"] += f" {clean}"

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return
        if tag in {"h3", "h4", "p", "small"}:
            self._mode = None
        if tag == "a":
            self.links.append(
                (
                    self._current["href"],
                    self._current["title"].strip(),
                    self._current["metadata"].strip(),
                    self._current["text"].strip(),
                )
            )
            self._current = None
            self._mode = None


def _parse(html: str) -> _LinkParser:
    parser = _LinkParser()
    parser.feed(html)
    parser.close()
    return parser


def parse_anime_results(html: str, base_url: str) -> list[AnimeResult]:
    results: list[AnimeResult] = []
    seen: set[str] = set()
    for href, title, metadata, text in _parse(html).links:
        if "/anime/" not in href:
            continue
        absolute = urljoin(base_url, href)
        if absolute in seen:
            continue
        title = title or text
        if not title or title.lower() == "dettagli":
            continue
        seen.add(absolute)
        results.append(AnimeResult(title, absolute, metadata))
    return results


def parse_episode_links(html: str, base_url: str) -> list[EpisodeRef]:
    episodes: dict[str, EpisodeRef] = {}
    pattern = re.compile(r"/episode/[^?#]*/ep-(\d+)(?:[/?#]|$)", re.I)
    for href, _title, _metadata, _text in _parse(html).links:
        match = pattern.search(href)
        if not match:
            continue
        number = match.group(1)
        episodes[number] = EpisodeRef(number, urljoin(base_url, href))
    return sorted(episodes.values(), key=lambda episode: (int(episode.number), episode.number))


def select_numbers(value: str, episodes: list[EpisodeRef]) -> list[EpisodeRef]:
    by_number = {episode.number: episode for episode in episodes}
    if value.strip().lower() == "all":
        return list(episodes)
    selected: dict[str, EpisodeRef] = {}
    for part in value.split(","):
        token = part.strip()
        if not token:
            continue
        numbers: Iterable[str]
        if "-" in token:
            start_text, end_text = (item.strip() for item in token.split("-", 1))
            if not start_text.isdigit() or not end_text.isdigit():
                return []
            start, end = sorted((int(start_text), int(end_text)))
            numbers = (str(number) for number in range(start, end + 1))
        elif token.isdigit():
            numbers = (token,)
        else:
            return []
        for number in numbers:
            if number not in by_number:
                return []
            selected[number] = by_number[number]
    return [episode for episode in episodes if episode.number in selected]


class AnimeCatalog:
    def __init__(self, base_url: str = "https://www.animesaturn.net") -> None:
        self.base_url = base_url.rstrip("/")

    async def search(self, title: str, timeout: float, headful: bool = False) -> list[AnimeResult]:
        html = await self._fetch(f"{self.base_url}/filter?key={quote(title)}", timeout, headful)
        return parse_anime_results(html, self.base_url)

    async def episodes(self, series_url: str, timeout: float, headful: bool = False) -> list[EpisodeRef]:
        html = await self._fetch(series_url, timeout, headful)
        return parse_episode_links(html, self.base_url)

    async def _fetch(self, url: str, timeout: float, headful: bool) -> str:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise CatalogError("Playwright is not installed; enter the Nix shell with `nix develop`") from exc
        deadline = monotonic() + timeout
        try:
            async with async_playwright() as playwright:
                executable = os.environ.get("CHROMIUM_EXECUTABLE_PATH") or shutil.which("chromium") or shutil.which("chromium-browser")
                options: dict[str, Any] = {"headless": not headful}
                if executable:
                    options["executable_path"] = executable
                browser = await playwright.chromium.launch(**options)
                try:
                    page = await browser.new_page()
                    await page.goto(url, wait_until="domcontentloaded", timeout=max(1000, int(max(0.1, deadline - monotonic()) * 1000)))
                    await page.wait_for_timeout(min(750, max(0, int((deadline - monotonic()) * 1000))))
                    return await page.content()
                finally:
                    await browser.close()
        except CatalogError:
            raise
        except Exception as exc:
            raise CatalogError(f"catalog page failed: {type(exc).__name__}") from exc
