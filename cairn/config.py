"""User-level configuration (~/.config/cairn/config.toml)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".config" / "cairn"
CONFIG_PATH = CONFIG_DIR / "config.toml"

# section -> allowed keys (None means accept any string key)
SECTION_KEYS: dict[str, set[str] | None] = {
    "agents": {"sources", "paths", "rescan"},
    "pricing": {"overrides", "edit_table"},
    "outcomes": {"test_command", "build_command", "git"},
    "optimize": {"auto", "backend", "holdout", "prune_threshold", "reflector", "reflector_key"},
    "budgets": {"daily_usd", "weekly_usd", "daily_tokens", "weekly_tokens", "min_quality"},
    "limits": {"five_hour_tokens"},
    "mcp": {"client", "auto_install"},
    "data": {"ledger", "re_ingest", "clear"},
    "diagnose": {
        "changepoint_multiplier",
        "cascade_k",
        "cascade_waste_threshold",
        "cascade_max_events",
        "cascade_lookahead",
        "context_rot_warning_pct",
        "context_rot_waste_pct",
    },
    "guard": {"allow_block", "tail_events"},
    "tests": None,
}

GUARD_DEFAULTS: dict[str, bool | int] = {
    "allow_block": False,
    "tail_events": 30,
}

DIAGNOSE_DEFAULTS: dict[str, float | int] = {
    "changepoint_multiplier": 2.0,
    "cascade_k": 3,
    "cascade_waste_threshold": 100,
    "cascade_max_events": 2000,
    "cascade_lookahead": 200,
    "context_rot_warning_pct": 70.0,
    "context_rot_waste_pct": 85.0,
}

VALID_SECTIONS = set(SECTION_KEYS)


def config_path() -> Path:
    return CONFIG_PATH


def load_config_dict() -> dict[str, dict[str, Any]]:
    """Load the full config as a dict of section dicts (defaults if absent/invalid)."""
    path = config_path()
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for k, v in data.items():
        if isinstance(v, dict):
            out[str(k)] = {str(sk): sv for sk, sv in v.items()}
    return out


def save_config_dict(data: dict[str, dict[str, Any]]) -> None:
    """Validate and persist ``data`` to config.toml."""
    validate(data)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config_path().write_text(dump_toml(data), encoding="utf-8")


def validate(data: dict[str, Any]) -> None:
    for section, body in data.items():
        if section not in VALID_SECTIONS:
            msg = f"unknown config section: {section!r}"
            raise ValueError(msg)
        if not isinstance(body, dict):
            msg = f"config section {section!r} must be a table"
            raise ValueError(msg)
        allowed = SECTION_KEYS[section]
        if allowed is None:
            continue
        for key in body:
            if key not in allowed:
                msg = f"unknown config key: {section}.{key}"
                raise ValueError(msg)


def get_setting(section: str, key: str, default: Any = None) -> Any:
    return load_config_dict().get(section, {}).get(key, default)


def mcp_auto_install_enabled() -> bool:
    """Default-on: auto-write MCP client config on first dashboard run."""
    val = get_setting("mcp", "auto_install", True)
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() not in ("false", "0", "no", "off")
    return bool(val)


def set_setting(section: str, key: str, value: Any) -> None:
    data = load_config_dict()
    data.setdefault(section, {})[key] = value
    save_config_dict(data)


def get_guard_setting(key: str, default: Any = None) -> Any:
    """Return a guard tunable (from config.toml or documented default)."""
    if default is None:
        default = GUARD_DEFAULTS.get(key)
    val = get_setting("guard", key, default)
    if key == "allow_block":
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() not in ("false", "0", "no", "off")
        return bool(val)
    if key == "tail_events":
        if isinstance(val, int) and not isinstance(val, bool):
            return val
        if isinstance(val, str):
            try:
                return int(val)
            except ValueError:
                return default
    return val if val is not None else default


def get_diagnose_setting(key: str) -> float | int:
    """Return a diagnose tunable (from config.toml or documented default)."""
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


# --- back-compat UserConfig adapter (gauge, outcomes/tests, CLI) ------------


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


def save_user_config(cfg: UserConfig) -> None:
    data: dict[str, dict[str, Any]] = dict(cfg.extra) if cfg.extra else {}
    data.setdefault("optimize", {})
    data["optimize"]["auto"] = cfg.optimize_auto
    if cfg.backend:
        data["optimize"]["backend"] = cfg.backend
    if cfg.five_hour_tokens is not None:
        data.setdefault("limits", {})["five_hour_tokens"] = cfg.five_hour_tokens
    # Drop tables we reconstruct so we never duplicate stale keys.
    save_config_dict(data)


def set_optimize_auto(value: bool) -> None:
    set_setting("optimize", "auto", bool(value))


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _str_or_none(value: Any) -> str | None:
    return str(value) if isinstance(value, str) else None


# --- minimal TOML emitter (stdlib only) -------------------------------------


def dump_toml(data: dict[str, Any]) -> str:
    lines: list[str] = ["# Cairn user configuration\n"]
    for section in sorted(data):
        body = data[section]
        if not isinstance(body, dict):
            continue
        lines.append(f"[{section}]")
        for key in sorted(body, key=str):
            lines.append(f"{key} = {_toml_value(body[key])}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{{{}}}".format(", ".join(f"{k} = {_toml_value(v)}" for k, v in value.items()))
    return '"' + str(value) + '"'
