"""SSE event models (Phase 3)."""

from pydantic import BaseModel


class ServerEvent(BaseModel):
    """Server-sent event envelope."""

    event: str
    data: dict[str, object]
