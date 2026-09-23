from __future__ import annotations

from typing import Any, Protocol


class ProviderExtractor(Protocol):
    def can_handle(self, frame_url: str) -> bool: ...

    async def interact(self, frame: Any, deadline: float) -> bool: ...

    async def extract(self, frame: Any, deadline: float) -> list[Any]: ...
