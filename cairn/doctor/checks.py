"""cairn doctor preflight checks (R18, §10)."""

from __future__ import annotations

from dataclasses import dataclass

from cairn.agents.profiles import check_profile
from cairn.doctor.mcp import check_mcp_server, load_agent_profiles, load_mcp_servers
from cairn.ingest.watch import watch_status
from cairn.model.project import Project
from cairn.providers.capabilities import get, infer_provider, strip_model_prefix
from cairn.providers.credentials import resolve_credentials

_MIN_REASONING_MAX_TOKENS = 4096


@dataclass(frozen=True)
class DoctorIssue:
    severity: str
    message: str


@dataclass(frozen=True)
class DoctorReport:
    issues: tuple[DoctorIssue, ...]

    @property
    def ok(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)


def run_doctor(project: Project) -> DoctorReport:
    issues: list[DoctorIssue] = []
    models_seen: set[str] = set()

    for step in project.steps.values():
        model = step.model or project.defaults_model
        if model in models_seen:
            continue
        models_seen.add(model)
        provider = infer_provider(model)
        cap = get(provider)
        creds = resolve_credentials(provider)
        if provider not in ("ollama",) and not creds.api_key:
            env = creds.key_env or "API_KEY"
            issues.append(
                DoctorIssue(
                    severity="error",
                    message=f"missing credential for provider {provider!r} (set {env})",
                )
            )
        if cap and cap.supported_models:
            wire = strip_model_prefix(model, cap)
            if wire not in cap.supported_models and model not in cap.supported_models:
                issues.append(
                    DoctorIssue(
                        severity="error",
                        message=f"unknown model {model!r} for provider {provider!r}",
                    )
                )
        if cap and cap.reasoning:
            params = step.params or project.defaults_params
            max_tokens = int(params.get("max_tokens", 0))
            if max_tokens < _MIN_REASONING_MAX_TOKENS:
                issues.append(
                    DoctorIssue(
                        severity="warning",
                        message=(
                            f"step {step.name!r} uses reasoning model {model!r} with "
                            f"max_tokens={max_tokens} (< {_MIN_REASONING_MAX_TOKENS}); "
                            "reasoning may exhaust the budget and return empty text"
                        ),
                    )
                )

    profile_ids = list(load_agent_profiles(project.root))
    watch = watch_status(project.root)
    if watch and not profile_ids:
        profile_ids = [s for s in watch.installed if s in ("claude-code", "codex", "cursor")]
    for profile_id in profile_ids:
        ok, message = check_profile(profile_id)
        issues.append(
            DoctorIssue(
                severity="error" if not ok else "info",
                message=message,
            )
        )

    mcp_servers = load_mcp_servers(project.root)
    if not mcp_servers:
        issues.append(
            DoctorIssue(
                severity="info",
                message="no MCP servers declared in cairn.toml ([mcp.servers])",
            )
        )
    for server in mcp_servers:
        ok, message = check_mcp_server(server)
        issues.append(
            DoctorIssue(
                severity="error" if not ok else "info",
                message=message,
            )
        )

    return DoctorReport(issues=tuple(issues))
