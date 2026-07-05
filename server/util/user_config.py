"""User-level configuration (~/.config/cairn/config.toml)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".config" / "cairn"
CONFIG_PATH = CONFIG_DIR / "config.toml"

DIAGNOSE_DEFAULTS: dict[str, float | int] = {
    "changepoint_multiplier": 2.0,
    "cascade_k": 3,
    "cascade_waste_threshold": 100,
    "cascade_max_events": 2000,
    "cascade_lookahead": 200,
    "context_rot_warning_pct": 70.0,
    "context_rot_waste_pct": 85.0,
}


def config_path() -> Path:
    return CONFIG_PATH


def load_config_dict() -> dict[str, dict[str, Any]]:
    """Load config as section dicts (empty if absent/invalid)."""
    path = config_path()
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            out[str(key)] = {str(sub_key): sub_val for sub_key, sub_val in value.items()}
    return out


def get_setting(section: str, key: str, default: Any = None) -> Any:
    return load_config_dict().get(section, {}).get(key, default)


def get_diagnose_setting(key: str) -> float | int:
    """Return a diagnose tunable from config.toml or documented default."""
    default = DIAGNOSE_DEFAULTS.get(key)
    if default is None:
        msg = f"unknown diagnose setting: {key}"
        raise KeyError(msg)
    val = get_setting("diagnose", key, default)
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return val
    if isinstance(val, str):
        try:
            if "." in val:
                return float(val)
            return int(val)
        except ValueError:
            return default
    return default


@dataclass
class UserConfig:
    optimize_auto: bool = False
    five_hour_tokens: int | None = None
    backend: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def load_user_config() -> UserConfig:
    data = load_config_dict()
    opt = data.get("optimize", {})
    limits = data.get("limits", {})
    return UserConfig(
        optimize_auto=bool(opt.get("auto", False)),
        five_hour_tokens=_int_or_none(limits.get("five_hour_tokens")),
        backend=_str_or_none(opt.get("backend")),
        extra=dict(data),
    )


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _str_or_none(value: Any) -> str | None:
    return str(value) if isinstance(value, str) else None
