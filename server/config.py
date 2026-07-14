"""Application configuration via pydantic-settings."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Cairn server settings loaded from env and optional config file."""

    model_config = SettingsConfigDict(
        env_prefix="CAIRN_",
        env_file=".env",
        extra="ignore",
    )

    host: str = Field(default="127.0.0.1", description="Bind address (loopback only by default)")
    port: int = Field(default=8787, description="HTTP port")
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

    def validate_bind(self) -> None:
        """Refuse non-loopback bind without token auth."""
        loopback_hosts = {"127.0.0.1", "localhost", "::1"}
        if self.host not in loopback_hosts and not self.token:
            msg = f"Refusing to bind to {self.host} without --token auth"
            raise ValueError(msg)


def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
