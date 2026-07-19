"""Advisory project policy evaluation (observed ≠ blocked)."""

from __future__ import annotations

import fnmatch
import re
from typing import Any, Literal

from server.configuration import (
    PolicyCommandRule,
    PolicyConfig,
    PolicyException,
)
from server.models.outcome import Outcome
from server.models.span import Span

EnforcementSource = Literal["observed_violation", "advisory_warning", "allowlisted_exception"]
ReviewRisk = Literal["none", "low", "medium", "high"]

_RISK_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3}


def evaluate_session_policy(
    *,
    spans: list[Span],
    outcome: Outcome | None,
    policy: PolicyConfig,
) -> dict[str, Any]:
    """Evaluate configured advisory policies against recorded session evidence.

    Findings never claim that Cairn blocked an action. ``enforcement_source`` states
    whether the signal is an observed ledger match, an advisory warning, or an
    allowlisted exception.
    """
    if not _policy_configured(policy):
        return {
            "evaluated": True,
            "review_risk": "none",
            "findings": [],
            "limitation": "No typed [policy] rules are configured for this workspace.",
            "enforcement_note": (
                "Cairn observes and advises; it does not claim to have blocked actions."
            ),
        }

    paths = _observed_paths(spans, outcome)
    commands = _observed_commands(spans)
    findings: list[dict[str, Any]] = []
    risk: ReviewRisk = "none"

    for path_rule in policy.path_risks:
        matched = [path for path in paths if _glob_match(path, path_rule.pattern)]
        if not matched:
            continue
        if _exception_covers_paths(policy.exceptions, matched):
            findings.append(
                _finding(
                    rule_id=f"path:{path_rule.pattern}",
                    risk=path_rule.risk,
                    message=(
                        f"Path risk {path_rule.risk} matched {matched[0]} but an exception applies."
                    ),
                    enforcement_source="allowlisted_exception",
                    evidence={"paths": matched[:5]},
                )
            )
            continue
        findings.append(
            _finding(
                rule_id=f"path:{path_rule.pattern}",
                risk=path_rule.risk,
                message=f"Observed path {matched[0]} matches risk={path_rule.risk} rule.",
                enforcement_source="observed_violation",
                evidence={"paths": matched[:5]},
            )
        )
        risk = _max_risk(risk, path_rule.risk)

    for command_rule in policy.commands:
        matched = [cmd for cmd in commands if _command_match(cmd, command_rule)]
        if not matched:
            continue
        if _exception_covers_commands(policy.exceptions, matched):
            findings.append(
                _finding(
                    rule_id=f"command:{command_rule.pattern}",
                    risk="high" if command_rule.mode == "forbidden" else "medium",
                    message=(
                        f"Command {matched[0]!r} matched {command_rule.mode} rule "
                        "but an exception applies."
                    ),
                    enforcement_source="allowlisted_exception",
                    evidence={"commands": matched[:5]},
                )
            )
            continue
        source: EnforcementSource = (
            "observed_violation" if command_rule.mode == "forbidden" else "advisory_warning"
        )
        findings.append(
            _finding(
                rule_id=f"command:{command_rule.pattern}",
                risk="high" if command_rule.mode == "forbidden" else "medium",
                message=(
                    f"Observed command {matched[0]!r} matches {command_rule.mode} policy"
                    + (f": {command_rule.reason}" if command_rule.reason else ".")
                ),
                enforcement_source=source,
                evidence={"commands": matched[:5]},
            )
        )
        risk = (
            _max_risk(risk, "high")
            if command_rule.mode == "forbidden"
            else _max_risk(risk, "medium")
        )

    if policy.max_changed_files is not None and outcome and outcome.files_changed is not None:
        count = len(outcome.files_changed)
        if count > policy.max_changed_files:
            findings.append(
                _finding(
                    rule_id="threshold:max_changed_files",
                    risk="high",
                    message=(
                        f"Observed {count} changed files exceeds policy max "
                        f"{policy.max_changed_files}."
                    ),
                    enforcement_source="observed_violation",
                    evidence={"changed_files": count},
                )
            )
            risk = _max_risk(risk, "high")

    for req in policy.required_checks:
        if not any(_glob_match(path, pat) for path in paths for pat in req.paths):
            continue
        missing = _missing_checks(req.checks, outcome, commands)
        if missing:
            findings.append(
                _finding(
                    rule_id=f"required_checks:{','.join(req.paths[:2])}",
                    risk="high",
                    message=(
                        "High-touch paths observed without recorded required checks: "
                        + ", ".join(missing)
                    ),
                    enforcement_source="advisory_warning",
                    evidence={"missing_checks": missing, "paths": req.paths},
                )
            )
            risk = _max_risk(risk, "high")

    return {
        "evaluated": True,
        "review_risk": risk,
        "findings": findings,
        "limitation": (
            "Policy findings are advisory observations from the local ledger. "
            "They do not prove Cairn blocked or prevented any action."
        ),
        "enforcement_note": (
            "enforcement_source is observed_violation, advisory_warning, or "
            "allowlisted_exception — never sandbox enforcement."
        ),
    }


def session_is_high_risk(risk_policy: dict[str, Any]) -> bool:
    return str(risk_policy.get("review_risk") or "") == "high"


def _policy_configured(policy: PolicyConfig) -> bool:
    return bool(
        policy.path_risks
        or policy.commands
        or policy.required_checks
        or policy.max_changed_files is not None
        or policy.network_deny
        or policy.dependency_deny
    )


def _finding(
    *,
    rule_id: str,
    risk: str,
    message: str,
    enforcement_source: EnforcementSource,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "risk": risk,
        "message": message,
        "enforcement_source": enforcement_source,
        "evidence": evidence,
    }


def _observed_paths(spans: list[Span], outcome: Outcome | None) -> list[str]:
    paths: list[str] = []
    if outcome and outcome.files_changed:
        paths.extend(str(path) for path in outcome.files_changed)
    for span in spans:
        if span.path_rel:
            paths.append(span.path_rel)
    # Preserve order, drop dupes.
    seen: set[str] = set()
    out: list[str] = []
    for path in paths:
        key = path.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def _observed_commands(spans: list[Span]) -> list[str]:
    commands: list[str] = []
    for span in spans:
        if span.kind != "tool_call" or not span.name:
            continue
        commands.append(span.name)
    return commands


def _glob_match(path: str, pattern: str) -> bool:
    return fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(path.split("/")[-1], pattern)


def _command_match(command: str, rule: PolicyCommandRule) -> bool:
    try:
        return re.search(rule.pattern, command, flags=re.I) is not None
    except re.error:
        return rule.pattern.lower() in command.lower()


def _exception_covers_paths(exceptions: list[PolicyException], paths: list[str]) -> bool:
    for exc in exceptions:
        for pattern in exc.paths:
            if any(_glob_match(path, pattern) for path in paths):
                return True
    return False


def _exception_covers_commands(exceptions: list[PolicyException], commands: list[str]) -> bool:
    for exc in exceptions:
        for pattern in exc.commands:
            try:
                if any(re.search(pattern, cmd, flags=re.I) for cmd in commands):
                    return True
            except re.error:
                if any(pattern.lower() in cmd.lower() for cmd in commands):
                    return True
    return False


def _missing_checks(required: list[str], outcome: Outcome | None, commands: list[str]) -> list[str]:
    missing: list[str] = []
    joined = " ".join(commands).lower()
    for check in required:
        key = check.lower()
        if key in {"test", "tests"}:
            if (outcome is None or outcome.tests_run is None) and (
                "pytest" not in joined and "vitest" not in joined and "test" not in joined
            ):
                missing.append(check)
            continue
        if key in {"build", "typecheck"}:
            if (outcome is None or outcome.build_status is None) and (
                key not in joined and "build" not in joined and "typecheck" not in joined
            ):
                missing.append(check)
            continue
        if key not in joined:
            missing.append(check)
    return missing


def _max_risk(current: ReviewRisk, candidate: str) -> ReviewRisk:
    if candidate not in _RISK_ORDER:
        return current
    if _RISK_ORDER[candidate] > _RISK_ORDER[current]:
        return candidate  # type: ignore[return-value]
    return current
