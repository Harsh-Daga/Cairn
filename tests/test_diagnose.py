"""Phase A — diagnosis tests."""

from __future__ import annotations

from cairn.diagnose.engine import compute_diagnostics
from cairn.diagnose.ideal import ideal_path_savings
from cairn.diagnose.localize import localize_failure
from cairn.diagnose.taxonomy import classify_failure
from cairn.outcomes.labels import derive_outcome_label


def _events_with_failure() -> list[dict]:
    return [
        {"event_id": 1, "seq": 1, "type": "user_prompt", "text_inline": "fix bug"},
        {
            "event_id": 2,
            "seq": 2,
            "type": "tool_call",
            "tool_norm_name": "read",
            "path_rel": "a.py",
        },
        {
            "event_id": 3,
            "seq": 3,
            "type": "tool_result",
            "tool_is_error": 1,
            "path_rel": "a.py",
            "waste_tokens": 500,
        },
        {
            "event_id": 4,
            "seq": 4,
            "type": "tool_call",
            "tool_norm_name": "bash",
            "tool_is_error": 1,
            "waste_tokens": 200,
        },
        {
            "event_id": 5,
            "seq": 5,
            "type": "tool_call",
            "tool_norm_name": "bash",
            "tool_is_error": 1,
        },
        {
            "event_id": 6,
            "seq": 6,
            "type": "tool_call",
            "tool_norm_name": "edit",
            "path_rel": "a.py",
        },
    ]


def test_localizer_points_at_early_error() -> None:
    events = _events_with_failure()
    eid, sig, _ = localize_failure(events)
    assert eid is not None
    assert sig is not None


def test_taxonomy_assigns_tool_misuse_on_errors() -> None:
    events = _events_with_failure()
    primary, _ = classify_failure(events, outcome_label="error_exit", failure_signature="x")
    assert primary == "tool_misuse"


def test_ideal_path_savings_non_negative() -> None:
    events = [
        {
            "seq": 1,
            "type": "tool_call",
            "tool_norm_name": "read",
            "path_rel": f"f{i}.py",
            "input_tokens": 100,
        }
        for i in range(10)
    ] + [
        {"seq": 11, "type": "tool_call", "tool_norm_name": "edit", "path_rel": "f0.py"},
    ]
    for i, e in enumerate(events, 1):
        e["event_id"] = i
    savings, explain = ideal_path_savings(events)
    assert savings >= 0
    assert explain["reads_actual"] >= explain["reads_ideal"]


def test_compute_diagnostics_landed_vs_failed() -> None:
    events = _events_with_failure()
    run = {"total_input_tokens": 1000, "total_output_tokens": 200, "status": "completed"}
    failed = compute_diagnostics(run, events, git_landed=False, tests_failed=2)
    assert failed["outcome_label"] != "landed"
    landed = compute_diagnostics(run, events, git_landed=True, tests_passed=5, tests_failed=0)
    assert landed["outcome_label"] == "landed"


def test_outcome_label_deterministic() -> None:
    label, source = derive_outcome_label(
        git_landed=True, tests_passed=1, tests_failed=0, status="completed", events=[]
    )
    assert label == "landed"
    assert source == "deterministic"
