"""Phase B — difficulty + normalized metrics."""

from __future__ import annotations

from cairn.metrics.difficulty import estimate_difficulty


def test_difficulty_buckets_differ_for_complexity() -> None:
    trivial_run = {"total_input_tokens": 100, "total_output_tokens": 50}
    trivial_events = [{"type": "user_prompt", "text_inline": "fix typo"}]
    hard_run = {"total_input_tokens": 50000, "total_output_tokens": 20000}
    hard_events = [
        {
            "type": "user_prompt",
            "text_inline": "migrate pyproject.toml and docker/kubernetes setup " * 20,
        },
        {"type": "tool_call", "tool_norm_name": "edit", "path_rel": "src/a/x.py"},
        {"type": "tool_call", "tool_norm_name": "edit", "path_rel": "src/b/y.py"},
        {"type": "tool_call", "tool_norm_name": "read", "path_rel": "src/c/z.py"},
    ]
    t = estimate_difficulty(trivial_run, trivial_events)
    h = estimate_difficulty(hard_run, hard_events)
    assert t.difficulty < h.difficulty
    assert t.bucket in ("trivial", "standard")
    assert h.bucket in ("hard", "epic", "standard")


def test_expectation_baselines_insufficient_below_n(tmp_path) -> None:
    import sqlite3

    from cairn.ledger.schema import migrate
    from cairn.metrics.normalized import get_expected, update_expectation_baselines

    conn = sqlite3.connect(tmp_path / "t.db")
    migrate(conn)
    for i in range(3):
        update_expectation_baselines(
            conn, model="m1", difficulty_bucket="standard", metric="total_tokens", value=1000.0 + i
        )
    exp = get_expected(conn, model="m1", difficulty_bucket="standard", metric="total_tokens")
    assert not exp.sufficient
    assert exp.data_notes
    conn.close()
