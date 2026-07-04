"""Pillar 1 tests — region decomposition + 5 detectors + re-billing $ + UNCLEARED."""

from __future__ import annotations

from cairn.metrics.waste import compute_waste
from cairn.pricing.data import match_model
from cairn.profile.decompose import decompose_session
from cairn.profile.detectors import (
    detect_context_fill_warning,
    detect_findings,
    detect_near_duplicate_from_text,
    rebilling_waste_tokens,
)


def _price(model: str) -> float:
    row = match_model(model)
    assert row is not None, f"no price for {model}"
    return row.input_per_mtok / 1_000_000.0


def _session(persistent_result_tokens: int = 1000, turns: int = 4):
    """A session whose tool_result persists across ``turns`` assistant turns."""
    events: list[dict] = []
    seq = 1

    def add(e):
        nonlocal seq
        e["seq"] = seq
        e["event_id"] = seq
        seq += 1
        events.append(e)

    add({"type": "user_prompt", "text_inline": "do thing"})
    add({"type": "tool_call", "tool_norm_name": "read", "path_rel": "a.py"})
    add(
        {
            "type": "tool_result",
            "tool_norm_name": "read",
            "path_rel": "a.py",
            "text_inline": "x" * 4000,
            "output_tokens": persistent_result_tokens,
        }
    )
    add({"type": "assistant_message", "text_inline": "ok", "input_tokens": 1200})
    for i in range(1, turns):
        add({"type": "user_prompt", "text_inline": f"q{i}"})
        add({"type": "assistant_message", "text_inline": f"a{i}", "input_tokens": 1200 + i})
    return events


def test_region_decomposition_emits_expected_regions() -> None:
    events = _session()
    res = decompose_session(
        events, model="claude-sonnet-4-5", input_price_per_token=_price("claude-sonnet-4-5")
    )
    region_names = {r.region for r in res.regions}
    assert "tool_result" in region_names
    assert "tool_schema" in region_names
    assert "user" in region_names
    assert "assistant_history" in region_names
    # 4 turns → tool_result region row appears in each turn after the first.
    tr_rows = [r for r in res.regions if r.region == "tool_result"]
    assert len(tr_rows) == 4
    assert res.turn_count == 4


def test_rebilling_dollar_math() -> None:
    events = _session(persistent_result_tokens=1000, turns=4)
    price = _price("claude-sonnet-4-5")
    res = decompose_session(events, model="claude-sonnet-4-5", input_price_per_token=price)
    # tool_result of 1000 tokens re-billed in turns 2,3,4 → 3000 re-billed tokens.
    assert res.rebilling_tokens >= 3000
    # The recoverable $ for the stale tool_result = 3000 * price.
    stale = rebilling_waste_tokens(events, res.regions)
    assert stale == 3000
    assert abs(res.rebilling_cost_usd - res.rebilling_tokens * price) < 1e-9


def test_duplicate_detector_fires_on_persistent_block() -> None:
    events = _session(turns=4)
    res = decompose_session(
        events, model="claude-sonnet-4-5", input_price_per_token=_price("claude-sonnet-4-5")
    )
    findings = detect_findings(
        events, res.regions, input_price_per_token=_price("claude-sonnet-4-5")
    )
    types = {f.type for f in findings}
    assert "DUPLICATE" in types
    dup = next(
        f for f in findings if f.type == "DUPLICATE" and f.detail.get("region") == "tool_result"
    )
    assert dup.tokens >= 3000


def test_stale_tool_result_detector() -> None:
    events = _session(turns=4)
    res = decompose_session(
        events, model="claude-sonnet-4-5", input_price_per_token=_price("claude-sonnet-4-5")
    )
    findings = detect_findings(
        events, res.regions, input_price_per_token=_price("claude-sonnet-4-5")
    )
    assert any(f.type == "STALE_TOOL_RESULT" for f in findings)


def test_near_duplicate_detector() -> None:
    a = ("tool_result", "the quick brown fox jumps over the lazy dog " * 4, 200)
    b = ("assistant_history", "the quick brown fox jumps over the lazy dog, " * 4, 200)
    findings = detect_near_duplicate_from_text([a, b], 3e-6)
    assert any(f.type == "NEAR_DUPLICATE" for f in findings)


def test_redundant_retrieval_detector() -> None:
    events: list[dict] = []
    seq = 1

    def add(e):
        nonlocal seq
        e["seq"] = seq
        e["event_id"] = seq
        seq += 1
        events.append(e)

    add({"type": "user_prompt", "text_inline": "find unused schema"})
    add({"type": "tool_call", "tool_norm_name": "search", "path_rel": "x.py"})
    add(
        {
            "type": "tool_result",
            "tool_norm_name": "search",
            "text_inline": "alpha beta gamma delta epsilon zeta",
        }
    )
    add(
        {
            "type": "assistant_message",
            "text_inline": "completely unrelated output about weather and rain",
        }
    )
    res = decompose_session(
        events, model="claude-sonnet-4-5", input_price_per_token=_price("claude-sonnet-4-5")
    )
    findings = detect_findings(
        events, res.regions, input_price_per_token=_price("claude-sonnet-4-5")
    )
    assert any(f.type == "REDUNDANT_RETRIEVAL" for f in findings)


def test_rebilling_waste_hook_in_compute_waste() -> None:
    """REBILLING_WASTE hook: passing rebilling_tokens adds to run_level + total."""
    events = _session(turns=4)
    res = decompose_session(
        events, model="claude-sonnet-4-5", input_price_per_token=_price("claude-sonnet-4-5")
    )
    stale = rebilling_waste_tokens(events, res.regions)
    assert stale > 0
    waste = compute_waste(events, has_cost=True, rebilling_tokens=stale)
    assert "rebilling_waste" in waste.run_level
    assert waste.total_waste_tokens >= stale


def test_uncleared_tool_result_signal() -> None:
    """A re-fetchable tool_result still in window ≥3 turns with no later edit."""
    events: list[dict] = []
    seq = 1

    def add(e):
        nonlocal seq
        e["seq"] = seq
        e["event_id"] = seq
        seq += 1
        events.append(e)

    add({"type": "user_prompt", "text_inline": "q1"})
    add({"type": "tool_call", "tool_norm_name": "read", "path_rel": "big.py"})
    add(
        {
            "type": "tool_result",
            "tool_norm_name": "read",
            "path_rel": "big.py",
            "text_inline": "x" * 2000,
        }
    )
    add({"type": "assistant_message", "text_inline": "a1"})
    for i in range(2, 6):
        add({"type": "user_prompt", "text_inline": f"q{i}"})
        add({"type": "assistant_message", "text_inline": f"a{i}"})
    waste = compute_waste(events, has_cost=True)
    cats = {c for _, c, _ in waste.tags}
    assert "uncleared_tool_result" in cats


def test_estimation_honesty_no_input_tokens() -> None:
    events: list[dict] = []
    seq = 1

    def add(e):
        nonlocal seq
        e["seq"] = seq
        e["event_id"] = seq
        seq += 1
        events.append(e)

    add({"type": "user_prompt", "text_inline": "q"})  # no input_tokens anywhere
    add({"type": "tool_call", "tool_norm_name": "read", "path_rel": "a.py"})
    add({"type": "tool_result", "tool_norm_name": "read", "text_inline": "x" * 200})
    add({"type": "assistant_message", "text_inline": "a"})
    res = decompose_session(events, model=None, input_price_per_token=None)
    assert res.estimated is True
    assert any("estimated" in n for n in res.data_notes)
    # No price → cost 0 + data-note.
    assert res.rebilling_cost_usd == 0.0
    assert any("input price unknown" in n for n in res.data_notes)


def test_profiler_context_fill_warning_at_70() -> None:
    """§2.7C: profiler warns at ≥70% (distinct from 85% waste CONTEXT_ROT)."""
    finding = detect_context_fill_warning(70.0)
    assert finding is not None
    assert finding.type == "CONTEXT_FILL_WARNING"
    assert detect_context_fill_warning(69.0) is None


def test_context_rot_waste_at_85_only() -> None:
    from cairn.metrics.waste import compute_waste

    events = [{"type": "user_prompt", "text_inline": "x"}]
    assert (
        "context_rot" not in compute_waste(events, has_cost=True, peak_context_pct=70.0).run_level
    )
    assert "context_rot" in compute_waste(events, has_cost=True, peak_context_pct=86.0).run_level
