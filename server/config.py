"""Application settings backed by the unified typed configuration contract."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from server.configuration import load_config


class Settings(BaseModel):
    """Resolved server settings; explicit constructor values have CLI-level precedence."""

    model_config = ConfigDict(extra="forbid")

    host: str = Field(default="127.0.0.1", description="Bind address (loopback only by default)")
    port: int = Field(default=8787, ge=1, le=65535, description="HTTP port")
    token: str | None = Field(default=None, description="Auth token for non-loopback bind")
    static_dir: Path = Field(
        default=Path(__file__).parent / "static",
        description="Built UI static assets directory",
    )
    workspace_root: Path | None = Field(default=None, description="Active workspace root path")
    outcome_revert_window_hours: int = Field(
        default=24,
        ge=1,
        le=168,
        description="Window for same-file revert/fixup outcome signals",
    )

    def __init__(self, **data: Any) -> None:
        root = data.get("workspace_root") or os.environ.get("CAIRN_WORKSPACE_ROOT")
        workspace_root = Path(root) if root is not None else None
        cli = {f"server.{key}": value for key, value in data.items()}
        resolved = load_config(workspace_root, cli_overrides=cli).server.model_dump()
        super().__init__(**resolved)

    def validate_bind(self) -> None:
        """Refuse non-loopback bind without token auth."""
        loopback_hosts = {"127.0.0.1", "localhost", "::1"}
        if self.host not in loopback_hosts and not self.token:
            msg = f"Refusing to bind to {self.host} without --token auth"
            raise ValueError(msg)


def get_settings() -> Settings:
    return Settings()
