"""Waste taxonomy tests — 7 categories + BLIND_RETRY + UNCLEARED_TOOL_RESULT."""

from __future__ import annotations

from cairn.metrics.waste import compute_waste


def _evt(seq: int, **kwargs):
    base = {"seq": seq, "type": "tool_call", "tool_norm_name": "read", "input_tokens": 1000}
    base.update(kwargs)
    return base


def test_identical_call_tags_duplicate() -> None:
    events = [
        _evt(1, text_hash="abc", tool_norm_name="read"),
        _evt(2, type="tool_result"),
        _evt(3, text_hash="abc", tool_norm_name="read"),
    ]
    result = compute_waste(events, has_cost=True)
    cats = {c for _, c, _ in result.tags}
    assert "identical_call" in cats


def test_retry_loop_detected() -> None:
    events = [
        _evt(1, tool_norm_name="bash"),
        {"seq": 2, "type": "tool_result", "tool_is_error": 1, "output_tokens": 50},
        _evt(3, tool_norm_name="bash"),
    ]
    result = compute_waste(events, has_cost=True)
    assert any(c == "retry_loop" for _, c, _ in result.tags)


def test_oversize_result() -> None:
    events = [
        {"seq": 1, "type": "tool_result", "output_tokens": 12000},
    ]
    result = compute_waste(events, has_cost=True)
    assert result.total_waste_tokens > 0


def test_stale_context_detected() -> None:
    events = [
        _evt(1, tool_norm_name="read", path_rel="src/app.py"),
        {"seq": 2, "type": "tool_result"},
        {"seq": 3, "type": "assistant_message"},
        _evt(4, tool_norm_name="read", path_rel="src/app.py"),  # gap 3 from seq 1
        {"seq": 5, "type": "tool_result"},
        {"seq": 6, "type": "assistant_message"},
        _evt(7, tool_norm_name="read", path_rel="src/app.py"),  # gap 3 from seq 4
    ]
    result = compute_waste(events, has_cost=True)
    assert any(c == "stale_context" for _, c, _ in result.tags)


def test_orientation_waste_detected() -> None:
    # 11 turns, first 3 are all read/search with no edits → orientation waste.
    events = []
    seq = 0
    for turn in range(11):
        seq += 1
        events.append({"seq": seq, "type": "user_prompt"})
        for _ in range(3):
            seq += 1
            norm = "read" if turn < 3 else "edit"
            events.append(_evt(seq, tool_norm_name=norm, input_tokens=500))
    result = compute_waste(events, has_cost=True)
    assert any(c == "orientation_waste" for _, c, _ in result.tags)


def test_context_rot_run_level() -> None:
    """CONTEXT_ROT fires at peak_context_pct > 85 (Part 9)."""
    events = [
        {"seq": 1, "type": "assistant_message", "context_tokens_after": 180_000},
        {"seq": 2, "type": "assistant_message", "context_tokens_after": 190_000},
    ]
    result = compute_waste(events, has_cost=True, peak_context_pct=90.0)
    assert "context_rot" in result.run_level


def test_context_rot_does_not_fire_below_threshold() -> None:
    events = [
        {"seq": 1, "type": "assistant_message", "context_tokens_after": 100_000},
    ]
    result = compute_waste(events, has_cost=True, peak_context_pct=80.0)
    assert "context_rot" not in result.run_level


def test_blind_retry_detected() -> None:
    """BLIND_RETRY: same tool + args within ≤2 turns (§2.7C Lucky-Pass signal)."""
    events = [
        _evt(1, text_hash="dup", tool_norm_name="bash"),
        _evt(2, text_hash="dup", tool_norm_name="bash"),  # gap = 1 → blind_retry
    ]
    result = compute_waste(events, has_cost=True)
    assert any(c == "blind_retry" for _, c, _ in result.tags)


def test_uncleared_tool_result_detected() -> None:
    """UNCLEARED_TOOL_RESULT: re-fetchable result still in window ≥3 turns after,
    no later edit depends on it."""
    events = [
        {"seq": 1, "type": "tool_result", "path_rel": "src/app.py", "text_inline": "X" * 4000},
        {"seq": 2, "type": "assistant_message"},
        {"seq": 3, "type": "assistant_message"},
        {"seq": 4, "type": "assistant_message"},
    ]
    result = compute_waste(events, has_cost=True)
    assert any(c == "uncleared_tool_result" for _, c, _ in result.tags)


def test_rebilling_waste_hook_returns_empty() -> None:
    """REBILLING_WASTE comes from the profiler (Phase B); the hook is empty now."""
    events = [{"seq": 1, "type": "assistant_message", "input_tokens": 100}]
    result = compute_waste(events, has_cost=True)  # no rebilling_tokens supplied
    assert "rebilling_waste" not in result.run_level
    # When supplied, it contributes to total and run_level.
    result2 = compute_waste(events, has_cost=True, rebilling_tokens=500)
    assert "rebilling_waste" in result2.run_level
    assert result2.total_waste_tokens >= 500


def test_cursor_no_token_waste_still_tags() -> None:
    events = [
        _evt(1, text_hash="x", input_tokens=0),
        _evt(2, type="tool_result", input_tokens=0),
        _evt(3, text_hash="x", input_tokens=0),
    ]
    result = compute_waste(events, has_cost=False)
    assert any(c == "identical_call" for _, c, t in result.tags if t == 0)


def test_has_cost_zero_count_only_path() -> None:
    """has_cost=0: structural waste fires by event counts with waste_tokens=0."""
    events = [
        _evt(1, text_hash="dup", tool_norm_name="bash"),
        _evt(2, text_hash="dup", tool_norm_name="bash"),
        {"seq": 3, "type": "tool_result", "output_tokens": 12000},
    ]
    result = compute_waste(events, has_cost=False)
    cats = {c for _, c, t in result.tags}
    # 1,2,4,5,8,9 still fire by structure
    assert "blind_retry" in cats or "identical_call" in cats
    assert "oversize_result" in cats
    # but no tokens attributed
    assert all(t == 0 for _, _, t in result.tags)
    assert result.total_waste_tokens == 0


def test_all_nine_signals_present() -> None:
    """The taxonomy exposes all 9 signal names across constructed scenarios."""
    from cairn.metrics.waste import compute_waste

    seen: set[str] = set()
    scenarios = [
        # 1 IDENTICAL_CALL
        [_evt(1, text_hash="a"), {"seq": 2, "type": "tool_result"}, _evt(3, text_hash="a")],
        # 2 RETRY_LOOP
        [
            _evt(1, tool_norm_name="bash"),
            {"seq": 2, "type": "tool_result", "tool_is_error": 1},
            _evt(3, tool_norm_name="bash"),
        ],
        # 3 OVERSIZE_RESULT
        [{"seq": 1, "type": "tool_result", "output_tokens": 12000}],
        # 4 STALE_CONTEXT
        [
            _evt(1, tool_norm_name="read", path_rel="p.py"),
            {"seq": 2, "type": "tool_result"},
            {"seq": 3, "type": "assistant_message"},
            _evt(4, tool_norm_name="read", path_rel="p.py"),
        ],
        # 5 ORIENTATION_WASTE (11 turns, first 3 read-heavy)
        _orientation_events(),
        # 6 CONTEXT_ROT
        [{"seq": 1, "type": "assistant_message", "context_tokens_after": 190_000}],
        # 8 BLIND_RETRY
        [
            _evt(1, text_hash="z", tool_norm_name="bash"),
            _evt(2, text_hash="z", tool_norm_name="bash"),
        ],
        # 9 UNCLEARED_TOOL_RESULT
        [
            {"seq": 1, "type": "tool_result", "path_rel": "p.py", "text_inline": "X" * 4000},
            {"seq": 2, "type": "assistant_message"},
            {"seq": 3, "type": "assistant_message"},
            {"seq": 4, "type": "assistant_message"},
        ],
    ]
    for events in scenarios:
        r = compute_waste(events, has_cost=True, peak_context_pct=95.0)
        for _, c, _ in r.tags:
            seen.add(c)
        for c in r.run_level:
            seen.add(c)
    # 7 REBILLING_WASTE via the hook input
    r = compute_waste([{"seq": 1, "type": "assistant_message"}], has_cost=True, rebilling_tokens=10)
    for c in r.run_level:
        seen.add(c)
    expected = {
        "identical_call",
        "retry_loop",
        "oversize_result",
        "stale_context",
        "orientation_waste",
        "context_rot",
        "rebilling_waste",
        "blind_retry",
        "uncleared_tool_result",
    }
    assert expected.issubset(seen), f"missing signals: {expected - seen}"


def _orientation_events():
    events = []
    seq = 0
    for turn in range(11):
        seq += 1
        events.append({"seq": seq, "type": "user_prompt"})
        for _ in range(3):
            seq += 1
            norm = "read" if turn < 3 else "edit"
            events.append(_evt(seq, tool_norm_name=norm, input_tokens=500))
    return events
