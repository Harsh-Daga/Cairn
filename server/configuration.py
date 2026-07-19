"""Typed, layered Cairn configuration with atomic comment-preserving mutations."""

from __future__ import annotations

import json
import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from server.util.private_files import ensure_private_dir, write_private_text

USER_CONFIG_PATH = Path.home() / ".config" / "cairn" / "config.toml"
WORKSPACE_CONFIG_REL = Path(".cairn") / "config.toml"


class ConfigError(ValueError):
    """Actionable configuration validation or mutation failure."""


class ServerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = "127.0.0.1"
    port: int = Field(default=8787, ge=1, le=65535)
    token: str | None = None
    static_dir: Path = Path(__file__).parent / "static"
    workspace_root: Path | None = None
    outcome_revert_window_hours: int = Field(default=24, ge=1, le=168)


class LimitsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    five_hour_tokens: int | None = Field(default=None, ge=1)


class BudgetsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    daily_usd: float | None = Field(default=None, ge=0)
    weekly_usd: float | None = Field(default=None, ge=0)
    monthly_usd: float | None = Field(default=None, ge=0)
    min_quality: float | None = Field(default=None, ge=0, le=1)


class OptimizeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auto: bool = False
    backend: str | None = None
    holdout: int = Field(default=8, ge=2, le=10_000)


class DiagnoseConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    changepoint_multiplier: float = Field(default=2.0, gt=0)
    cascade_k: int = Field(default=3, ge=1, le=100)
    cascade_waste_threshold: int = Field(default=100, ge=0)
    cascade_max_events: int = Field(default=2000, ge=1, le=1_000_000)
    cascade_lookahead: int = Field(default=200, ge=1, le=100_000)
    context_rot_warning_pct: float = Field(default=70.0, ge=0, le=100)
    context_rot_waste_pct: float = Field(default=85.0, ge=0, le=100)


class McpConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auto_install: bool = False
    client: Literal["claude-code", "cursor", "codex", "other"] = "cursor"


class PricingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)
    stale_after_days: int = Field(
        default=90,
        ge=1,
        le=3650,
        description="Warn when bundled price table effective_date is older than this many days.",
    )


class PolicyPathRisk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pattern: str
    risk: Literal["low", "medium", "high"] = "medium"


class PolicyCommandRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pattern: str
    mode: Literal["forbidden", "advisory"] = "advisory"
    reason: str | None = None


class PolicyRequiredCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paths: list[str] = Field(default_factory=list)
    checks: list[str] = Field(default_factory=list)


class PolicyException(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    reason: str
    paths: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)


class PolicyConfig(BaseModel):
    """Advisory workspace policy. Observation never implies Cairn blocked an action."""

    model_config = ConfigDict(extra="forbid")

    path_risks: list[PolicyPathRisk] = Field(default_factory=list)
    commands: list[PolicyCommandRule] = Field(default_factory=list)
    required_checks: list[PolicyRequiredCheck] = Field(default_factory=list)
    network_deny: list[str] = Field(default_factory=list)
    dependency_deny: list[str] = Field(default_factory=list)
    max_changed_files: int | None = Field(default=None, ge=1, le=100_000)
    exceptions: list[PolicyException] = Field(default_factory=list)


class CollectionConfig(BaseModel):
    """Backend auto-sync collection mode (independent of browser Live updates / SSE)."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["manual", "efficient", "live"] = "efficient"


class ResourcesConfig(BaseModel):
    """Soft local resource budgets (advisory warnings; no silent deletion)."""

    model_config = ConfigDict(extra="forbid")

    soft_budget_bytes: int | None = Field(default=None, ge=1)
    max_file_bytes: int = Field(
        default=32 * 1024 * 1024,
        ge=1024,
        le=512 * 1024 * 1024,
        description="Reject/quarantine source files larger than this before parse.",
    )
    max_parse_ms: int = Field(
        default=30_000,
        ge=100,
        le=600_000,
        description="Wall-clock budget for one adapter.parse_path call.",
    )
    max_consecutive_failures: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Pause an adapter after this many consecutive parse/budget failures.",
    )


class JobsConfig(BaseModel):
    """Bounded async action executor (not a daemon/service)."""

    model_config = ConfigDict(extra="forbid")

    max_workers: int = Field(default=2, ge=1, le=16)
    max_queued: int = Field(default=8, ge=1, le=256)
    result_ttl_sec: int = Field(default=3600, ge=60, le=86400)
    default_timeout_sec: int | None = Field(default=900, ge=1, le=86_400)


class StorageConfig(BaseModel):
    """Raw content retention: Metrics / Balanced (default) / Forensic."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["metrics", "balanced", "forensic", "reference"] = "balanced"
    text_inline_max: int | None = Field(default=None, ge=0, le=1_000_000)
    scrub_at_ingest: bool = False
    balanced_retain_days: int = Field(default=14, ge=1, le=3650)


class LifecycleConfig(BaseModel):
    """Warn-only data lifecycle until destructive ops are explicitly enabled."""

    model_config = ConfigDict(extra="forbid")

    destructive_enabled: bool = False
    default_retain_days: int = Field(default=90, ge=1, le=3650)


class CairnConfig(BaseModel):
    """Typed known sections plus preserved forward-compatible extension sections."""

    model_config = ConfigDict(extra="allow")

    server: ServerConfig = Field(default_factory=ServerConfig)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    budgets: BudgetsConfig = Field(default_factory=BudgetsConfig)
    optimize: OptimizeConfig = Field(default_factory=OptimizeConfig)
    diagnose: DiagnoseConfig = Field(default_factory=DiagnoseConfig)
    mcp: McpConfig = Field(default_factory=McpConfig)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)
    collection: CollectionConfig = Field(default_factory=CollectionConfig)
    resources: ResourcesConfig = Field(default_factory=ResourcesConfig)
    jobs: JobsConfig = Field(default_factory=JobsConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    lifecycle: LifecycleConfig = Field(default_factory=LifecycleConfig)
    tests: dict[str, str] = Field(default_factory=dict)
    pricing: PricingConfig = Field(default_factory=PricingConfig)


@dataclass(frozen=True, slots=True)
class ResolvedValue:
    key: str
    value: Any
    source: Literal["cli", "environment", "workspace", "user", "default"]
    secret: bool

    def public_value(self, *, reveal_secrets: bool = False) -> Any:
        if self.secret and self.value is not None and not reveal_secrets:
            return "<redacted>"
        return self.value


ALIASES = {
    "host": "server.host",
    "port": "server.port",
    "token": "server.token",
    "static_dir": "server.static_dir",
    "workspace_root": "server.workspace_root",
    "outcome_revert_window_hours": "server.outcome_revert_window_hours",
    "test_command": "tests.default",
    "optimize_auto": "optimize.auto",
    "five_hour_tokens": "limits.five_hour_tokens",
}

ENV_KEYS = {
    "CAIRN_HOST": "server.host",
    "CAIRN_PORT": "server.port",
    "CAIRN_TOKEN": "server.token",
    "CAIRN_STATIC_DIR": "server.static_dir",
    "CAIRN_WORKSPACE_ROOT": "server.workspace_root",
    "CAIRN_OUTCOME_REVERT_WINDOW_HOURS": "server.outcome_revert_window_hours",
    "CAIRN_LIMITS_FIVE_HOUR_TOKENS": "limits.five_hour_tokens",
    "CAIRN_OPTIMIZE_AUTO": "optimize.auto",
    "CAIRN_OPTIMIZE_BACKEND": "optimize.backend",
}

_FIXED_SECTIONS: dict[str, type[BaseModel]] = {
    "server": ServerConfig,
    "limits": LimitsConfig,
    "budgets": BudgetsConfig,
    "optimize": OptimizeConfig,
    "diagnose": DiagnoseConfig,
    "mcp": McpConfig,
    "policy": PolicyConfig,
    "collection": CollectionConfig,
    "resources": ResourcesConfig,
    "jobs": JobsConfig,
    "storage": StorageConfig,
    "lifecycle": LifecycleConfig,
}
_SECRET_PARTS = ("token", "secret", "password", "api_key", "apikey")
_SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]\s*(?:#.*)?$")


def user_config_path() -> Path:
    return USER_CONFIG_PATH


def workspace_config_path(workspace_root: Path) -> Path:
    return workspace_root.expanduser().resolve() / WORKSPACE_CONFIG_REL


def canonical_key(key: str) -> str:
    cleaned = key.strip().lower().replace("-", "_")
    return ALIASES.get(cleaned, cleaned)


def is_secret_key(key: str) -> bool:
    leaf = canonical_key(key).rsplit(".", 1)[-1]
    return leaf in _SECRET_PARTS or any(leaf.endswith(f"_{part}") for part in _SECRET_PARTS)


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except OSError as exc:
        raise ConfigError(f"Cannot read configuration {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {path}: {exc}") from exc
    normalized = {str(key): value for key, value in data.items()}
    for alias, canonical in ALIASES.items():
        if alias in normalized and not isinstance(normalized[alias], dict):
            _set_nested(normalized, canonical, normalized.pop(alias))
    return normalized


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _set_nested(data: dict[str, Any], key: str, value: Any) -> None:
    parts = canonical_key(key).split(".")
    cursor = data
    for part in parts[:-1]:
        child = cursor.setdefault(part, {})
        if not isinstance(child, dict):
            raise ConfigError(f"{'.'.join(parts[:-1])} is not a configuration section")
        cursor = child
    cursor[parts[-1]] = value


def _get_nested(data: dict[str, Any], key: str) -> Any:
    cursor: Any = data
    for part in canonical_key(key).split("."):
        if not isinstance(cursor, dict) or part not in cursor:
            raise KeyError(key)
        cursor = cursor[part]
    return cursor


def _parse_scalar(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value


def _validate_key(key: str) -> str:
    canonical = canonical_key(key)
    parts = canonical.split(".")
    if len(parts) < 2:
        raise ConfigError(
            f"Unknown configuration key {key!r}; use a dotted key such as server.host"
        )
    section, leaf = parts[0], parts[1]
    if section in _FIXED_SECTIONS:
        if len(parts) != 2 or leaf not in _FIXED_SECTIONS[section].model_fields:
            raise ConfigError(f"Unknown configuration key {key!r}")
    elif section == "tests":
        if len(parts) != 2 or not leaf:
            raise ConfigError("Test commands use tests.<project> or tests.default")
    elif section == "pricing":
        if len(parts) < 4 or parts[1] != "overrides":
            raise ConfigError(
                "Pricing keys use pricing.overrides.<model>.<field>; nested writes are not yet "
                "supported by `config set`"
            )
        raise ConfigError(
            "Set pricing overrides in [pricing.overrides.<model>] TOML; `config set` preserves "
            "only scalar section keys"
        )
    else:
        raise ConfigError(f"Unknown configuration section {section!r}")
    return canonical


def _validate(data: dict[str, Any]) -> CairnConfig:
    try:
        return CairnConfig.model_validate(data)
    except ValidationError as exc:
        first = exc.errors(include_url=False)[0]
        location = ".".join(str(part) for part in first["loc"])
        raise ConfigError(f"Invalid configuration for {location}: {first['msg']}") from exc


def _env_overlay(environ: dict[str, str]) -> dict[str, Any]:
    overlay: dict[str, Any] = {}
    for env_name, key in ENV_KEYS.items():
        if env_name in environ:
            _set_nested(overlay, key, _parse_scalar(environ[env_name]))
    return overlay


def load_config(
    workspace_root: Path | None = None,
    *,
    cli_overrides: dict[str, Any] | None = None,
    environ: dict[str, str] | None = None,
) -> CairnConfig:
    """Resolve defaults < user < workspace < environment < explicit CLI values."""
    data: dict[str, Any] = {}
    data = _deep_merge(data, _read_toml(user_config_path()))
    if workspace_root is not None:
        data = _deep_merge(data, _read_toml(workspace_config_path(workspace_root)))
    data = _deep_merge(data, _env_overlay(dict(os.environ if environ is None else environ)))
    for key, value in (cli_overrides or {}).items():
        if value is not None:
            _set_nested(data, _validate_key(key), value)
    return _validate(data)


def resolved_values(
    workspace_root: Path | None = None,
    *,
    cli_overrides: dict[str, Any] | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, ResolvedValue]:
    """Return flattened validated values with their winning source."""
    env = dict(os.environ if environ is None else environ)
    user = _read_toml(user_config_path())
    workspace = _read_toml(workspace_config_path(workspace_root)) if workspace_root else {}
    resolved = load_config(workspace_root, cli_overrides=cli_overrides, environ=env)
    flat: dict[str, ResolvedValue] = {}
    for key, value in _flatten(resolved.model_dump(mode="json")).items():
        source: Literal["cli", "environment", "workspace", "user", "default"] = "default"
        if _contains(user, key):
            source = "user"
        if _contains(workspace, key):
            source = "workspace"
        if any(mapped == key and name in env for name, mapped in ENV_KEYS.items()):
            source = "environment"
        if cli_overrides and any(canonical_key(candidate) == key for candidate in cli_overrides):
            source = "cli"
        flat[key] = ResolvedValue(key, value, source, is_secret_key(key))
    return flat


def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, value in data.items():
        key = f"{prefix}.{name}" if prefix else name
        if isinstance(value, dict) and value:
            out.update(_flatten(value, key))
        elif not isinstance(value, dict):
            out[key] = value
    return out


def _contains(data: dict[str, Any], key: str) -> bool:
    try:
        _get_nested(data, key)
    except KeyError:
        return False
    return True


def get_config_value(
    key: str,
    workspace_root: Path | None = None,
    *,
    reveal_secrets: bool = False,
) -> dict[str, Any]:
    canonical = _validate_key(key)
    values = resolved_values(workspace_root)
    if canonical not in values:
        raise ConfigError(f"Configuration key {canonical!r} has no scalar value")
    item = values[canonical]
    return {
        "key": canonical,
        "value": item.public_value(reveal_secrets=reveal_secrets),
        "source": item.source,
        "secret": item.secret,
    }


def list_config_values(
    workspace_root: Path | None = None, *, reveal_secrets: bool = False
) -> list[dict[str, Any]]:
    return [
        {
            "key": item.key,
            "value": item.public_value(reveal_secrets=reveal_secrets),
            "source": item.source,
            "secret": item.secret,
        }
        for item in sorted(resolved_values(workspace_root).values(), key=lambda item: item.key)
    ]


def mutate_config(
    operation: Literal["set", "unset"],
    key: str,
    *,
    value: Any = None,
    workspace_root: Path | None = None,
    scope: Literal["user", "workspace"] = "user",
) -> dict[str, Any]:
    canonical = _validate_key(key)
    path = (
        user_config_path()
        if scope == "user"
        else workspace_config_path(workspace_root or Path.cwd())
    )
    parsed = _parse_scalar(value)
    prospective = _read_toml(path)
    if operation == "set":
        _set_nested(prospective, canonical, parsed)
    else:
        _delete_nested(prospective, canonical)
    _validate(prospective)
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    updated = _edit_scalar_toml(text, canonical, parsed, unset=operation == "unset")
    ensure_private_dir(path.parent)
    write_private_text(path, updated)
    return {
        "operation": operation,
        "key": canonical,
        "value": "<redacted>" if is_secret_key(canonical) and operation == "set" else parsed,
        "scope": scope,
        "path": str(path),
    }


def _delete_nested(data: dict[str, Any], key: str) -> None:
    parts = key.split(".")
    cursor: Any = data
    for part in parts[:-1]:
        if not isinstance(cursor, dict) or part not in cursor:
            return
        cursor = cursor[part]
    if isinstance(cursor, dict):
        cursor.pop(parts[-1], None)


def _toml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if value is None:
        raise ConfigError("TOML has no null value; use `config unset`")
    if not isinstance(value, str):
        raise ConfigError("config set supports boolean, number, and string values")
    return json.dumps(value, ensure_ascii=False)


def _edit_scalar_toml(text: str, key: str, value: Any, *, unset: bool) -> str:
    section, leaf = key.split(".", 1)
    lines = text.splitlines()
    section_start: int | None = None
    section_end = len(lines)
    for index, line in enumerate(lines):
        match = _SECTION_RE.match(line)
        if not match:
            continue
        if section_start is not None:
            section_end = index
            break
        if match.group(1).strip() == section:
            section_start = index
    assignment = re.compile(rf"^\s*{re.escape(leaf)}\s*=")
    if section_start is not None:
        for index in range(section_start + 1, section_end):
            if assignment.match(lines[index]):
                if unset:
                    del lines[index]
                else:
                    comment = ""
                    if " #" in lines[index]:
                        comment = " #" + lines[index].split(" #", 1)[1]
                    lines[index] = f"{leaf} = {_toml_scalar(value)}{comment}"
                return "\n".join(lines).rstrip() + "\n"
        if not unset:
            lines.insert(section_end, f"{leaf} = {_toml_scalar(value)}")
    elif not unset:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend((f"[{section}]", f"{leaf} = {_toml_scalar(value)}"))
    return "\n".join(lines).rstrip() + ("\n" if lines else "")


def configuration_reference_markdown() -> str:
    """Generate the fixed-key reference from Pydantic schemas."""
    lines = [
        "# Generated configuration reference",
        "",
        "Generated from `server.configuration`; edit the schema, not this table.",
        "",
        "| Key | Type | Default | Secret |",
        "|---|---|---|---|",
    ]
    defaults = CairnConfig().model_dump(mode="json")
    for section, model in _FIXED_SECTIONS.items():
        for name, field_info in model.model_fields.items():
            key = f"{section}.{name}"
            annotation = (
                str(field_info.annotation)
                .replace("typing.", "")
                .replace("<class '", "")
                .replace("'>", "")
                .replace(" | None", "?")
                # Python 3.13 stringifies pathlib.Path as pathlib._local.Path.
                .replace("pathlib._local.Path", "pathlib.Path")
            )
            default = _get_nested(defaults, key)
            if is_secret_key(key):
                shown = "`<redacted>`"
            elif key == "server.static_dir":
                shown = "`<package>/server/static`"
            else:
                shown = f"`{default!r}`"
            lines.append(
                f"| `{key}` | `{annotation}` | {shown} | {'yes' if is_secret_key(key) else 'no'} |"
            )
    lines.extend(
        (
            "| `tests.<project>` | `str` | — | no |",
            "| `pricing.overrides.<model>.<field>` | typed price row | — | key-dependent |",
            "",
        )
    )
    return "\n".join(lines)
