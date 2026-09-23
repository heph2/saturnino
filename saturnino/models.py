from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RequestObservation:
    request_url: str
    response_url: str | None = None
    status: int | None = None
    content_type: str | None = None
    content_length: int | None = None
    content_range_total: int | None = None
    resource_type: str | None = None
    frame_id: str | None = None
    frame_url: str | None = None
    page_id: str | None = None
    redirect_chain: list[str] = field(default_factory=list)
    player_frame: bool = False
    interaction_time: float | None = None
    started_at: float = 0.0
    sequence: int = 0
    failed_reason: str | None = None
    ad_evidence: bool = False

    @property
    def final_url(self) -> str:
        return self.response_url or self.request_url


@dataclass(slots=True)
class ScoreResult:
    score: int
    reasons: list[str]
    eligible: bool
    media_type: str


@dataclass(slots=True)
class ValidationResult:
    state: str
    reason: str
    checked_url: str | None = None
    final_url: str | None = None
    status: int | None = None


@dataclass(slots=True)
class MediaCandidate:
    url: str
    media_type: str
    score: int
    reasons: list[str] = field(default_factory=list)
    status: int | None = None
    content_type: str | None = None
    content_length: int | None = None
    content_range_total: int | None = None
    resource_type: str | None = None
    frame_id: str | None = None
    frame_url: str | None = None
    player_frame: bool = False
    sequence: int = 0
    validation: ValidationResult | None = None
    eligible: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "media_type": self.media_type,
            "score": self.score,
            "reasons": self.reasons,
            "status": self.status,
            "content_type": self.content_type,
            "content_length": self.content_length,
            "validation": self.validation.state if self.validation else "not_attempted",
        }


@dataclass(slots=True)
class EpisodeMetadata:
    title: str | None
    episode: str | None


@dataclass(slots=True)
class ExtractionResult:
    title: str | None
    episode: str | None
    provider: str | None
    selected: MediaCandidate | None
    candidates: list[MediaCandidate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        selected = self.selected
        return {
            "title": self.title,
            "episode": self.episode,
            "provider": self.provider,
            "media_type": selected.media_type if selected else None,
            "url": selected.url if selected else None,
            "score": selected.score if selected else None,
            "validation": selected.validation.state if selected and selected.validation else "not_attempted",
            "warnings": self.warnings,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }
