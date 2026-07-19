"""Compatibility accessors for the unified typed configuration contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from server.configuration import USER_CONFIG_PATH, DiagnoseConfig, load_config

CONFIG_DIR = USER_CONFIG_PATH.parent
CONFIG_PATH = USER_CONFIG_PATH

DIAGNOSE_DEFAULTS: dict[str, float | int] = {
    key: value
    for key, value in DiagnoseConfig().model_dump().items()
    if isinstance(value, (int, float))
}


def config_path() -> Path:
    return CONFIG_PATH


def load_config_dict() -> dict[str, dict[str, Any]]:
    return load_config().model_dump()


def get_setting(section: str, key: str, default: Any = None) -> Any:
    section_data = load_config_dict().get(section, {})
    return section_data.get(key, default)


def get_diagnose_setting(key: str) -> float | int:
    data = load_config().diagnose.model_dump()
    if key not in data:
        msg = f"unknown diagnose setting: {key}"
        raise KeyError(msg)
    value = data[key]
    if not isinstance(value, (int, float)):
        raise TypeError(key)
    return value


@dataclass
class UserConfig:
    optimize_auto: bool = False
    five_hour_tokens: int | None = None
    backend: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def load_user_config() -> UserConfig:
    config = load_config()
    return UserConfig(
        optimize_auto=config.optimize.auto,
        five_hour_tokens=config.limits.five_hour_tokens,
        backend=config.optimize.backend,
        extra=config.model_dump(),
    )
