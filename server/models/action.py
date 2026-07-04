"""Action registry models (Phase 7)."""

from pydantic import BaseModel


class ActionManifestEntry(BaseModel):
    """Registered action descriptor."""

    name: str
    title: str
    category: str
