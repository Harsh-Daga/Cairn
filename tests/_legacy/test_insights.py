"""Insights rules tests — 12 rules + cache health + savings cap."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cairn.insights.engine import evaluate, render_feed
from cairn.insights.rules import ALL_RULES
from cairn.ledger.ledger import Ledger
from cairn.ledger.schema import migrate


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _day(offset: int) -> str:
    return (datetime.now(UTC) - timedelta(days=offset)).isoformat()


def _insert_run(
    conn: sqlite3.Connection,
    run_id: str,
    *,
    source: str = "claude-code",
    model: str = "claude-opus",
    started_at: str | None = None,
    input_tokens: int = 100_000,
    output_tokens: int = 20_000,
    cost: float = 5.0,
    has_cost: int = 1,
    peak: float | None = None,
    cache_read: int = 0,
    cache_creation: int = 0,
) -> None:
    conn.execute(
        """
        INSERT INTO runs (
          run_id, source, external_id, started_at, status,
          total_input_tokens, total_output_tokens, total_cost, has_cost,
          peak_context_pct, cache_read_tokens, cache_creation_tokens, model
        ) VALUES (?, ?, ?, ?, 'completed', ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            source,
            run_id,
            started_at or _now(),
            input_tokens,
            output_tokens,
            cost,
            has_cost,
            peak,
            cache_read,
            cache_creation,
            model,
        ),
    )


def _ids(insights) -> set[str]:
    return {i.id for i in insights}


def _by_id(insights, key: str):
    return next((i for i in insights if i.id == key), None)


# ---------------------------------------------------------------------------
# 1. Context window pressure
# ---------------------------------------------------------------------------


def test_insights_context_pressure_error(tmp_path) -> None:
    db = tmp_path / ".cairn" / "ledger.db"
    db.parent.mkdir()
    conn = sqlite3.connect(db)
    migrate(conn)
    _insert_run(conn, "r1", peak=90.0)
    conn.commit()
    conn.close()
    ledger = Ledger(db)
    insights = evaluate(ledger, days=14)
    ledger.close()
    assert "context-window-pressure" in _ids(insights)
    cp = _by_id(insights, "context-window-pressure")
    assert cp.severity == "error"


def test_insights_context_pressure_warning(tmp_path) -> None:
    db = tmp_path / ".cairn" / "ledger.db"
    db.parent.mkdir()
    conn = sqlite3.connect(db)
    migrate(conn)
    _insert_run(conn, "r1", peak=80.0)
    conn.commit()
    conn.close()
    ledger = Ledger(db)
    insights = evaluate(ledger, days=14)
    ledger.close()
    cp = _by_id(insights, "context-window-pressure")
    assert cp is not None and cp.severity == "warning"


def test_insights_context_rot_warning_at_70(tmp_path) -> None:
    """§2.7C: context-rot warning trigger fires at >=70% fill (distinct from
    the 85% run-level waste category in metrics/waste.py)."""
    db = tmp_path / ".cairn" / "ledger.db"
    db.parent.mkdir()
    conn = sqlite3.connect(db)
    migrate(conn)
    _insert_run(conn, "r1", peak=70.0)
    conn.commit()
    conn.close()
    ledger = Ledger(db)
    insights = evaluate(ledger, days=14)
    ledger.close()
    cp = _by_id(insights, "context-window-pressure")
    assert cp is not None and cp.severity == "warning"
    assert cp.evidence["peak_context_pct"] == 70.0


def test_insights_context_rot_below_70_silent(tmp_path) -> None:
    db = tmp_path / ".cairn" / "ledger.db"
    db.parent.mkdir()
    conn = sqlite3.connect(db)
    migrate(conn)
    _insert_run(conn, "r1", peak=69.0)
    conn.commit()
    conn.close()
    ledger = Ledger(db)
    insights = evaluate(ledger, days=14)
    ledger.close()
    assert _by_id(insights, "context-window-pressure") is None


# ---------------------------------------------------------------------------
# 2. Identical tool calls
# ---------------------------------------------------------------------------


def test_insights_identical_tool_calls(tmp_path) -> None:
    db = tmp_path / ".cairn" / "ledger.db"
    db.parent.mkdir()
    conn = sqlite3.connect(db)
    migrate(conn)
    _insert_run(conn, "r1", input_tokens=200_000, cost=10.0)
    conn.execute(
        "INSERT INTO events (run_id, seq, type, waste_category, waste_tokens, tool_norm_name) "
        "VALUES ('r1', 1, 'tool_call', 'identical_call', 50000, 'search')"
    )
    conn.commit()
    conn.close()
    ledger = Ledger(db)
    insights = evaluate(ledger, days=14)
    ledger.close()
    rule = _by_id(insights, "identical-tool-calls")
    assert rule is not None and rule.severity == "warning"
    assert rule.savings_estimate is not None and rule.savings_estimate > 0


def test_insights_identical_tool_calls_no_cost_data_note(tmp_path) -> None:
    db = tmp_path / ".cairn" / "ledger.db"
    db.parent.mkdir()
    conn = sqlite3.connect(db)
    migrate(conn)
    _insert_run(conn, "r1", input_tokens=200_000, cost=0.0, has_cost=0)
    conn.execute(
        "INSERT INTO events (run_id, seq, type, waste_category, waste_tokens, tool_norm_name) "
        "VALUES ('r1', 1, 'tool_call', 'identical_call', 50000, 'search')"
    )
    conn.commit()
    conn.close()
    ledger = Ledger(db)
    insights = evaluate(ledger, days=14)
    ledger.close()
    rule = _by_id(insights, "identical-tool-calls")
    assert rule is not None
    assert rule.savings_estimate is None
    assert "data_notes" in rule.evidence


# ---------------------------------------------------------------------------
# 3. Oversize tool results
# ---------------------------------------------------------------------------


def test_insights_oversize_tool_results(tmp_path) -> None:
    db = tmp_path / ".cairn" / "ledger.db"
    db.parent.mkdir()
    conn = sqlite3.connect(db)
    migrate(conn)
    _insert_run(conn, "r1", input_tokens=200_000, cost=10.0)
    conn.execute(
        "INSERT INTO events (run_id, seq, type, waste_category, waste_tokens, tool_norm_name) "
        "VALUES ('r1', 1, 'tool_result', 'oversize_result', 30000, 'read')"
    )
    conn.commit()
    conn.close()
    ledger = Ledger(db)
    insights = evaluate(ledger, days=14)
    ledger.close()
    assert "oversize-tool-results" in _ids(insights)


# ---------------------------------------------------------------------------
# 4. High file churn
# ---------------------------------------------------------------------------


def test_insights_high_file_churn(tmp_path) -> None:
    db = tmp_path / ".cairn" / "ledger.db"
    db.parent.mkdir()
    conn = sqlite3.connect(db)
    migrate(conn)
    _insert_run(conn, "r1")
    for seq in range(1, 7):
        conn.execute(
            "INSERT INTO events (run_id, seq, type, tool_norm_name, path_rel) "
            "VALUES ('r1', ?, 'tool_call', 'edit', 'src/x.py')",
            (seq,),
        )
    conn.commit()
    conn.close()
    ledger = Ledger(db)
    insights = evaluate(ledger, days=14)
    ledger.close()
    assert "high-file-churn" in _ids(insights)


# ---------------------------------------------------------------------------
# 5. Retry loops
# ---------------------------------------------------------------------------


def test_insights_retry_loops(tmp_path) -> None:
    db = tmp_path / ".cairn" / "ledger.db"
    db.parent.mkdir()
    conn = sqlite3.connect(db)
    migrate(conn)
    _insert_run(conn, "r1")
    for seq in range(1, 8):
        conn.execute(
            "INSERT INTO events (run_id, seq, type, waste_category, waste_tokens) "
            "VALUES ('r1', ?, 'tool_call', 'retry_loop', 0)",
            (seq,),
        )
    conn.commit()
    conn.close()
    ledger = Ledger(db)
    insights = evaluate(ledger, days=14)
    ledger.close()
    rl = _by_id(insights, "retry-loops-detected")
    assert rl is not None and rl.severity == "warning"


# ---------------------------------------------------------------------------
# 6. Cache misuse — writes without reads, prefix mismatch, creation spike
# ---------------------------------------------------------------------------


def test_insights_cache_misuse_writes_no_reads(tmp_path) -> None:
    db = tmp_path / ".cairn" / "ledger.db"
    db.parent.mkdir()
    conn = sqlite3.connect(db)
    migrate(conn)
    _insert_run(conn, "r1", cache_read=0, cache_creation=5000, started_at=_day(1))
    conn.commit()
    conn.close()
    ledger = Ledger(db)
    insights = evaluate(ledger, days=14)
    ledger.close()
    cm = _by_id(insights, "cache-misuse")
    assert cm is not None
    assert "writing but not reading" in cm.body


def test_insights_cache_prefix_mismatch(tmp_path) -> None:
    db = tmp_path / ".cairn" / "ledger.db"
    db.parent.mkdir()
    conn = sqlite3.connect(db)
    migrate(conn)
    # hit rate = 100 / (100 + 1000) = 0.091 < 0.80 over a day → prefix mismatch.
    _insert_run(conn, "r1", cache_read=100, cache_creation=1000, started_at=_day(1))
    conn.commit()
    conn.close()
    ledger = Ledger(db)
    insights = evaluate(ledger, days=14)
    ledger.close()
    cm = _by_id(insights, "cache-misuse")
    assert cm is not None
    assert "prefix mismatch" in cm.body.lower()


def test_insights_cache_creation_spike(tmp_path) -> None:
    db = tmp_path / ".cairn" / "ledger.db"
    db.parent.mkdir()
    conn = sqlite3.connect(db)
    migrate(conn)
    _insert_run(conn, "r1", cache_creation=600, started_at=_day(1))
    # An event-level cache-creation spike: 600 cache_creation vs 1000 input → 60%.
    conn.execute(
        "INSERT INTO events (run_id, seq, type, cache_creation_tokens, input_tokens) "
        "VALUES ('r1', 1, 'assistant_message', 600, 1000)"
    )
    conn.commit()
    conn.close()
    ledger = Ledger(db)
    insights = evaluate(ledger, days=14)
    ledger.close()
    cm = _by_id(insights, "cache-misuse")
    assert cm is not None
    assert "thrash" in cm.body.lower()
    assert cm.evidence.get("spike_count") == 1


# ---------------------------------------------------------------------------
# 7. Multi-model cost spread
# ---------------------------------------------------------------------------


def test_insights_multi_model_spread(tmp_path) -> None:
    db = tmp_path / ".cairn" / "ledger.db"
    db.parent.mkdir()
    conn = sqlite3.connect(db)
    migrate(conn)
    _insert_run(conn, "r1", model="claude-opus", cost=10.0, started_at=_day(5))
    _insert_run(conn, "r2", model="claude-sonnet", cost=2.0, started_at=_day(5))
    _insert_run(conn, "r3", model="gpt-4o", cost=5.0, started_at=_day(5))
    conn.commit()
    conn.close()
    ledger = Ledger(db)
    insights = evaluate(ledger, days=14)
    ledger.close()
    assert "multi-model-cost-spread" in _ids(insights)


# ---------------------------------------------------------------------------
# 8. Runaway sessions
# ---------------------------------------------------------------------------


def test_insights_runaway_sessions(tmp_path) -> None:
    db = tmp_path / ".cairn" / "ledger.db"
    db.parent.mkdir()
    conn = sqlite3.connect(db)
    migrate(conn)
    _insert_run(conn, "r1", input_tokens=10_000)
    # 6 assistant turns: first 3 input=100, last 3 input=500 → ratio 5x.
    for seq, inp in enumerate([100, 100, 100, 500, 500, 500], start=1):
        conn.execute(
            "INSERT INTO events (run_id, seq, type, input_tokens) "
            "VALUES ('r1', ?, 'assistant_message', ?)",
            (seq, inp),
        )
    conn.commit()
    conn.close()
    ledger = Ledger(db)
    insights = evaluate(ledger, days=14)
    ledger.close()
    rw = _by_id(insights, "runaway-sessions")
    assert rw is not None and rw.severity == "warning"
    assert rw.evidence["worst_ratio"] > 3.0


# ---------------------------------------------------------------------------
# 9. Rebilling waste
# ---------------------------------------------------------------------------


def _add_turn(
    conn,
    run_id,
    seq,
    *,
    prompt=True,
    tool_call=None,
    tool_result=None,
    assistant=True,
    assistant_text="ok",
) -> int:
    """Insert one turn's events starting at ``seq``; return the next free seq."""
    s = seq
    if prompt:
        conn.execute(
            "INSERT INTO events (run_id, seq, type, text_inline) "
            "VALUES (?, ?, 'user_prompt', 'do')",
            (run_id, s),
        )
        s += 1
    if tool_call:
        conn.execute(
            "INSERT INTO events (run_id, seq, type, tool_norm_name, path_rel) "
            "VALUES (?, ?, 'tool_call', ?, ?)",
            (run_id, s, tool_call, "src/x.py"),
        )
        s += 1
    if tool_result:
        conn.execute(
            "INSERT INTO events (run_id, seq, type, tool_norm_name, path_rel, "
            "text_inline, output_tokens) "
            "VALUES (?, ?, 'tool_result', ?, ?, ?, ?)",
            (run_id, s, tool_result, "src/x.py", tool_result, 0),
        )
        s += 1
    if assistant:
        conn.execute(
            "INSERT INTO events (run_id, seq, type, text_inline) "
            "VALUES (?, ?, 'assistant_message', ?)",
            (run_id, s, assistant_text),
        )
        s += 1
    return s


def test_insights_rebilling_waste(tmp_path) -> None:
    db = tmp_path / ".cairn" / "ledger.db"
    db.parent.mkdir()
    conn = sqlite3.connect(db)
    migrate(conn)
    _insert_run(conn, "r1", input_tokens=500_000, cost=20.0)
    big = "x" * 70_000  # ~17,500 tokens per tool_result region
    # Turn 1 produces a big tool_result; turns 2-4 have no new result so the
    # same content_hash re-bills each turn and stays stale (no edit to x).
    seq = 1
    seq = _add_turn(conn, "r1", seq, tool_call="read", tool_result=big, assistant=True)
    for _ in range(3):
        seq = _add_turn(conn, "r1", seq, tool_call=None, tool_result=None, assistant=True)
    conn.commit()
    conn.close()
    ledger = Ledger(db)
    insights = evaluate(ledger, days=14)
    ledger.close()
    rb = _by_id(insights, "rebilling-waste")
    assert rb is not None
    assert rb.evidence["rebilled_tokens"] > 50_000


# ---------------------------------------------------------------------------
# 10. Behavioral drift (gradual, via fingerprints)
# ---------------------------------------------------------------------------


def _insert_fingerprint(conn, run_id, week, dim0, project="p", model="m") -> None:
    vec = [float(dim0)] + [0.0] * 23
    conn.execute(
        """
        INSERT INTO fingerprints (run_id, project, model, source, ts, vector_json, week)
        VALUES (?, ?, ?, 'claude-code', ?, ?, ?)
        """,
        (run_id, project, model, _day(1), json.dumps(vec), week),
    )


def test_insights_behavioral_drift(tmp_path) -> None:
    db = tmp_path / ".cairn" / "ledger.db"
    db.parent.mkdir()
    conn = sqlite3.connect(db)
    migrate(conn)
    # 4 weekly means; dim0 jumps in the last two weeks → gradual drift.
    _insert_fingerprint(conn, "f1", "2026-W24", 0.0)
    _insert_fingerprint(conn, "f2", "2026-W25", 0.0)
    _insert_fingerprint(conn, "f3", "2026-W26", 10.0)
    _insert_fingerprint(conn, "f4", "2026-W27", 10.0)
    conn.commit()
    conn.close()
    ledger = Ledger(db)
    insights = evaluate(ledger, days=14)
    ledger.close()
    bd = _by_id(insights, "behavioral-drift")
    assert bd is not None and bd.severity == "warning"
    assert bd.evidence.get("top_dims")


# ---------------------------------------------------------------------------
# 11. Quality regression
# ---------------------------------------------------------------------------


def test_insights_quality_regression(tmp_path) -> None:
    db = tmp_path / ".cairn" / "ledger.db"
    db.parent.mkdir()
    conn = sqlite3.connect(db)
    migrate(conn)
    # Prior 7-14d: quality 80. Recent 0-7d: quality 60 → 25% drop.
    for i, offset in enumerate([8, 9, 10]):
        _insert_run(conn, f"prior{i}", started_at=_day(offset))
        conn.execute(
            "INSERT INTO outcomes (run_id, quality_score, captured_at) VALUES (?, 80.0, ?)",
            (f"prior{i}", _day(offset)),
        )
    for i, offset in enumerate([1, 2, 3]):
        _insert_run(conn, f"recent{i}", started_at=_day(offset))
        conn.execute(
            "INSERT INTO outcomes (run_id, quality_score, captured_at) VALUES (?, 60.0, ?)",
            (f"recent{i}", _day(offset)),
        )
    conn.commit()
    conn.close()
    ledger = Ledger(db)
    insights = evaluate(ledger, days=14)
    ledger.close()
    qr = _by_id(insights, "quality-regression")
    assert qr is not None and qr.severity == "warning"
    assert qr.evidence["drop_pct"] > 15.0


# ---------------------------------------------------------------------------
# 12. Unused tools
# ---------------------------------------------------------------------------


def test_insights_unused_tools(tmp_path) -> None:
    db = tmp_path / ".cairn" / "ledger.db"
    db.parent.mkdir()
    conn = sqlite3.connect(db)
    migrate(conn)
    _insert_run(conn, "r1")
    # 10 turns, one bash call in turn 1 → use_fraction 0.1 → UNUSED_TOOL_SCHEMA.
    seq = 1
    seq = _add_turn(conn, "r1", seq, tool_call="bash", assistant=True)
    for _ in range(9):
        seq = _add_turn(conn, "r1", seq, assistant=True)
    conn.commit()
    conn.close()
    ledger = Ledger(db)
    insights = evaluate(ledger, days=14)
    ledger.close()
    ut = _by_id(insights, "unused-tools")
    assert ut is not None
    assert "bash" in ut.body


# ---------------------------------------------------------------------------
# Empty state + rule count + savings cap
# ---------------------------------------------------------------------------


def test_insights_empty_state(tmp_path, capsys) -> None:
    db = tmp_path / ".cairn" / "ledger.db"
    db.parent.mkdir()
    conn = sqlite3.connect(db)
    migrate(conn)
    conn.commit()
    conn.close()
    ledger = Ledger(db)
    insights = evaluate(ledger, days=14)
    ledger.close()
    assert insights == []
    render_feed(insights)
    out = capsys.readouterr().out
    assert "No issues detected" in out


def test_insights_exactly_13_rules() -> None:
    assert len(ALL_RULES) == 13


def test_subagent_heavy_fires(tmp_path: Path) -> None:
    import sqlite3

    from cairn.insights.engine import evaluate
    from cairn.ledger.ledger import Ledger
    from cairn.ledger.schema import migrate

    db = tmp_path / ".cairn" / "ledger.db"
    db.parent.mkdir()
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    migrate(conn)
    conn.execute(
        "INSERT INTO runs (run_id, source, external_id, started_at, status, has_cost, "
        "total_input_tokens, total_output_tokens, total_cost) "
        "VALUES ('r-sub', 'claude-code', 'e-sub', datetime('now'), 'completed', 1, 1000, 500, 1.0)"
    )
    conn.execute(
        "INSERT INTO diagnostics (run_id, outcome_label, label_source, computed_at) "
        "VALUES ('r-sub', 'abandoned', 'deterministic', datetime('now'))"
    )
    for seq, lane, tok in ((1, "main", 50), (2, "sidechain", 900), (3, "sidechain", 400)):
        conn.execute(
            "INSERT INTO events (run_id, seq, type, agent_lane, agent_id, "
            "input_tokens, output_tokens) "
            "VALUES ('r-sub', ?, 'assistant_message', ?, ?, ?, ?)",
            (seq, lane, f"agent-{lane}", tok, 10),
        )
    conn.commit()
    conn.close()
    ledger = Ledger(db)
    try:
        insights = evaluate(ledger, days=14)
    finally:
        ledger.close()
    hit = [i for i in insights if i.id == "subagent-heavy"]
    assert hit


def test_subagent_heavy_silent_on_main_only(tmp_path: Path) -> None:
    import sqlite3

    from cairn.insights.engine import evaluate
    from cairn.ledger.ledger import Ledger
    from cairn.ledger.schema import migrate

    db = tmp_path / ".cairn" / "ledger.db"
    db.parent.mkdir()
    conn = sqlite3.connect(db)
    migrate(conn)
    conn.execute(
        "INSERT INTO runs (run_id, source, external_id, started_at, status, has_cost) "
        "VALUES ('r-main', 'claude-code', 'e-main', datetime('now'), 'completed', 0)"
    )
    conn.execute(
        "INSERT INTO diagnostics (run_id, outcome_label, label_source, computed_at) "
        "VALUES ('r-main', 'abandoned', 'deterministic', datetime('now'))"
    )
    conn.execute(
        "INSERT INTO events (run_id, seq, type, agent_lane, input_tokens, output_tokens) "
        "VALUES ('r-main', 1, 'assistant_message', 'main', 500, 100)"
    )
    conn.commit()
    conn.close()
    ledger = Ledger(db)
    try:
        insights = evaluate(ledger, days=14)
    finally:
        ledger.close()
    assert not any(i.id == "subagent-heavy" for i in insights)


def test_insights_savings_capped_at_50pct(tmp_path) -> None:
    db = tmp_path / ".cairn" / "ledger.db"
    db.parent.mkdir()
    conn = sqlite3.connect(db)
    migrate(conn)
    # Small spend, large re-billed token volume priced → savings must cap at
    # 50% of weekly spend.
    _insert_run(conn, "r1", input_tokens=500_000, cost=4.0)
    big = "x" * 70_000
    seq = 1
    seq = _add_turn(conn, "r1", seq, tool_call="read", tool_result=big, assistant=True)
    for _ in range(3):
        seq = _add_turn(conn, "r1", seq, assistant=True)
    conn.commit()
    conn.close()
    ledger = Ledger(db)
    insights = evaluate(ledger, days=14)
    ledger.close()
    rb = _by_id(insights, "rebilling-waste")
    assert rb is not None
    if rb.savings_estimate is not None:
        weekly_spend = 4.0 * (7 / 14)
        assert rb.savings_estimate <= weekly_spend * 0.5 + 0.01
