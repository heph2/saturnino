from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from .models import RequestObservation
from .scoring import classify_media_type, is_eligible, rank_candidates


class NetworkInterceptor:
    """Collect context-wide network metadata without retaining response bodies."""

    def __init__(self, debug: Callable[[str, dict[str, Any]], None] | None = None) -> None:
        self.observations: list[RequestObservation] = []
        self._by_request: dict[int, RequestObservation] = {}
        self._frame_ids: dict[int, str] = {}
        self._page_ids: dict[int, str] = {}
        self._player_frames: set[str] = set()
        self._interaction_times: dict[str, float] = {}
        self._sequence = 0
        self._debug = debug
        self.version = 0

    def attach(self, context: Any) -> None:
        context.on("request", self.on_request)
        context.on("response", self.on_response)
        context.on("requestfailed", self.on_request_failed)

    def register_page(self, page: Any, page_id: str) -> None:
        self._page_ids[id(page)] = page_id

    def mark_player_frame(self, frame: Any, frame_id: str | None = None) -> str:
        identifier = frame_id or self.frame_id(frame)
        if identifier:
            self._player_frames.add(identifier)
            for observation in self.observations:
                if observation.frame_id == identifier:
                    observation.player_frame = True
        return identifier or ""

    def add_dom_media(self, url: str, frame: Any) -> None:
        if not url.startswith(("http://", "https://")):
            return
        frame_id = self.frame_id(frame)
        self._sequence += 1
        self.observations.append(RequestObservation(
            request_url=url,
            response_url=url,
            frame_id=frame_id,
            frame_url=getattr(frame, "url", None),
            player_frame=frame_id in self._player_frames,
            interaction_time=self._interaction_times.get(frame_id or ""),
            started_at=time.monotonic(),
            sequence=self._sequence,
        ))
        self.version += 1

    def mark_interaction(self, frame: Any) -> None:
        identifier = self.frame_id(frame)
        if identifier:
            self._interaction_times[identifier] = time.monotonic()

    def frame_id(self, frame: Any) -> str | None:
        if frame is None:
            return None
        key = id(frame)
        if key not in self._frame_ids:
            self._frame_ids[key] = f"frame-{len(self._frame_ids) + 1}"
        return self._frame_ids[key]

    def _frame_snapshot(self, request: Any) -> tuple[str | None, str | None, str | None]:
        try:
            frame = request.frame
            frame_id = self.frame_id(frame)
            frame_url = frame.url if frame else None
            page_id = self._page_ids.get(id(frame.page)) if frame else None
            return frame_id, frame_url, page_id
        except Exception as exc:
            self._log("frame_snapshot_failed", error=type(exc).__name__)
            return None, None, None

    def on_request(self, request: Any) -> None:
        self._sequence += 1
        frame_id, frame_url, page_id = self._frame_snapshot(request)
        started = time.monotonic()
        interaction = self._interaction_times.get(frame_id or "")
        inferred_player = self._looks_like_player(frame_url)
        if inferred_player and frame_id:
            self._player_frames.add(frame_id)
        observation = RequestObservation(
            request_url=request.url,
            resource_type=getattr(request, "resource_type", None),
            frame_id=frame_id,
            frame_url=frame_url,
            page_id=page_id,
            player_frame=frame_id in self._player_frames or inferred_player,
            interaction_time=interaction,
            started_at=started,
            sequence=self._sequence,
        )
        redirects: list[str] = []
        try:
            previous = request.redirected_from
            while previous is not None:
                redirects.append(previous.url)
                previous = previous.redirected_from
        except Exception:
            pass
        observation.redirect_chain = list(reversed(redirects))
        self._by_request[id(request)] = observation
        self.observations.append(observation)
        if len(self.observations) > 10_000:
            self.observations = self.observations[-10_000:]
        self._log("request", url=request.url, resource_type=observation.resource_type, frame_id=frame_id)

    def on_response(self, response: Any) -> None:
        observation = self._by_request.get(id(response.request))
        if observation is None:
            self.on_request(response.request)
            observation = self._by_request.get(id(response.request))
        if observation is None:
            return
        observation.response_url = response.url
        observation.status = getattr(response, "status", None)
        try:
            headers = response.headers
            observation.content_type = headers.get("content-type")
            raw_length = headers.get("content-length")
            observation.content_length = int(raw_length) if raw_length and raw_length.isdigit() else None
            content_range = headers.get("content-range", "")
            if "/" in content_range:
                total = content_range.rsplit("/", 1)[1]
                observation.content_range_total = int(total) if total.isdigit() else None
        except (AttributeError, TypeError, ValueError) as exc:
            self._log("response_headers_failed", error=type(exc).__name__)
        observation.player_frame = observation.player_frame or observation.frame_id in self._player_frames
        self.version += 1
        media_type = classify_media_type(observation.final_url, observation.content_type)
        if is_eligible(observation) and media_type != "unknown":
            self._log("media_candidate", media_type=media_type, status=observation.status)
        self._log("response", status=observation.status, resource_type=observation.resource_type)

    def on_request_failed(self, request: Any) -> None:
        observation = self._by_request.get(id(request))
        if observation:
            observation.failed_reason = getattr(request, "failure", None)
            self._log("request_failed", error=observation.failed_reason)

    def candidates(self):
        return rank_candidates(self.observations)

    @staticmethod
    def _looks_like_player(frame_url: str | None) -> bool:
        if not frame_url:
            return False
        lowered = frame_url.lower()
        return "/embed/" in lowered or "/player/" in lowered

    def _log(self, event: str, **fields: Any) -> None:
        if self._debug:
            self._debug(event, fields)
