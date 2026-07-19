"""Advisory policy evaluation and check integration."""

from __future__ import annotations

from server.analyze.policy import evaluate_session_policy
from server.configuration import (
    PolicyCommandRule,
    PolicyConfig,
    PolicyException,
    PolicyPathRisk,
    PolicyRequiredCheck,
)
from server.models.outcome import Outcome
from server.models.span import Span


def test_empty_policy_evaluates_with_limitation() -> None:
    result = evaluate_session_policy(spans=[], outcome=None, policy=PolicyConfig())
    assert result["evaluated"] is True
    assert result["review_risk"] == "none"
    assert result["findings"] == []
    assert "blocked" not in result["limitation"].lower()


def test_path_and_forbidden_command_findings() -> None:
    spans = [
        Span(
            span_id="s1",
            trace_id="t1",
            seq=1,
            kind="tool_call",
            name="rm -rf /tmp/x",
            status="ok",
            path_rel="src/auth/session.py",
        )
    ]
    outcome = Outcome(
        trace_id="t1",
        files_changed=["src/auth/session.py"],
        tests_run=None,
        build_status=None,
    )
    policy = PolicyConfig(
        path_risks=[PolicyPathRisk(pattern="**/auth/**", risk="high")],
        commands=[PolicyCommandRule(pattern=r"rm\s+-rf", mode="forbidden", reason="destructive")],
        required_checks=[PolicyRequiredCheck(paths=["**/auth/**"], checks=["tests", "build"])],
    )
    result = evaluate_session_policy(spans=spans, outcome=outcome, policy=policy)
    assert result["review_risk"] == "high"
    sources = {f["enforcement_source"] for f in result["findings"]}
    assert "observed_violation" in sources
    assert "advisory_warning" in sources
    assert all("blocked" not in f["message"].lower() for f in result["findings"])


def test_exception_allowlists_without_claiming_enforcement() -> None:
    spans = [
        Span(
            span_id="s1",
            trace_id="t1",
            seq=1,
            kind="tool_call",
            name="rm -rf build",
            status="ok",
            path_rel="build/tmp",
        )
    ]
    policy = PolicyConfig(
        commands=[PolicyCommandRule(pattern=r"rm\s+-rf", mode="forbidden")],
        exceptions=[
            PolicyException(
                id="build-clean",
                reason="local build cleanup",
                commands=[r"rm\s+-rf"],
            )
        ],
    )
    result = evaluate_session_policy(spans=spans, outcome=None, policy=policy)
    assert result["findings"]
    assert result["findings"][0]["enforcement_source"] == "allowlisted_exception"
