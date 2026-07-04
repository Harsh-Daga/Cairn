"""Tests for the managed instruction block (cairn/optimize/block.py)."""

from __future__ import annotations

import pytest

from cairn.optimize.apply import (
    MANAGED_END,
    MANAGED_START,
    BlockError,
    Entry,
    consolidate,
    has_block,
    parse_block,
    replace_block,
    serialize_block,
)


def _entry(kind: str, eid: str, content: str, conf: float = 0.9) -> Entry:
    return Entry(kind=kind, entry_id=eid, content=content, confidence=conf)


def test_serialize_then_parse_roundtrips() -> None:
    entries = [
        _entry("command_fix", "pnpm-test", "Use `pnpm test -w` (not `npm test`)."),
        _entry("known_issue", "make-build", "`make build` fails on ARM; use `make build-x86`."),
        _entry("file_guide", "schema", "`cairn/ledger/schema.py`: SQLite DDL + migrations."),
    ]
    block = serialize_block(entries)
    assert MANAGED_START in block and MANAGED_END in block
    parsed = parse_block(block)
    assert {(e.kind, e.entry_id) for e in parsed} == {(e.kind, e.entry_id) for e in entries}
    assert {e.content for e in parsed} == {e.content for e in entries}


def test_replace_block_preserves_surrounding_text() -> None:
    original = "# My project\n\nSome human notes.\n"
    entries = [_entry("file_guide", "x", "`x.py`: does the thing.")]
    updated = replace_block(original, entries)
    assert updated.startswith("# My project")
    assert "Some human notes." in updated
    assert has_block(updated)
    # Replacing again with the same entries is idempotent.
    assert replace_block(updated, entries) == updated


def test_replace_block_swaps_existing_block_only() -> None:
    base = replace_block("# Title\n\nbody\n", [_entry("file_guide", "a", "`a.py`: A.")])
    swapped = replace_block(base, [_entry("file_guide", "b", "`b.py`: B.")])
    parsed = parse_block(swapped)
    assert [e.entry_id for e in parsed] == ["b"]
    assert "body" in swapped
    assert swapped.count(MANAGED_START) == 1
    assert swapped.count(MANAGED_END) == 1


def test_parse_ignores_text_outside_markers() -> None:
    text = (
        "Before.\n- Use `fake` <!-- cairn:entry command_fix/decoy -->\n"
        + serialize_block([_entry("known_issue", "real", "Real issue.")])
        + "\nAfter.\n"
    )
    parsed = parse_block(text)
    assert [e.entry_id for e in parsed] == ["real"]


def test_corrupt_markers_refuse() -> None:
    with pytest.raises(BlockError):
        parse_block(f"{MANAGED_START}\nstuff with no end\n")
    with pytest.raises(BlockError):
        parse_block(f"{MANAGED_END}\nend before start\n")
    with pytest.raises(BlockError):
        # Nested starts.
        parse_block(f"{MANAGED_START}\n{MANAGED_START}\n{MANAGED_END}\n")


def test_confidence_parsed_from_marker() -> None:
    block = serialize_block([_entry("command_fix", "c", "Use `c`.", conf=0.73)])
    parsed = parse_block(block)
    assert parsed[0].confidence == pytest.approx(0.73)


def test_consolidate_merges_near_duplicates() -> None:
    entries = [
        _entry("file_guide", "a", "`a.py`: does A.", conf=0.9),
        _entry("file_guide", "a", "`a.py`: does A.", conf=0.5),  # duplicate id
    ]
    out = consolidate(entries)
    assert len(out) == 1
    # Highest confidence wins.
    assert out[0].confidence == pytest.approx(0.9)


def test_consolidate_drops_lowest_confidence_over_cap() -> None:
    # 200 entries blow past MANAGED_BLOCK_MAX_LINES; consolidation trims to the cap.
    entries = [
        _entry("file_guide", f"id{i}", f"`f{i}.py`: file {i}.", conf=i / 200.0) for i in range(200)
    ]
    out = consolidate(entries)
    block = serialize_block(out)
    assert block.count("\n") <= 120
    assert len(block) <= 6000
    # The entries kept are the highest-confidence ones.
    kept_ids = {e.entry_id for e in out}
    assert "id199" in kept_ids
    assert "id0" not in kept_ids


def test_double_apply_is_identical() -> None:
    entries = [
        _entry("command_fix", "c", "Use `c`."),
        _entry("file_guide", "f", "`f.py`: F."),
    ]
    once = replace_block("# T\n\nx\n", entries)
    twice = replace_block(once, parse_block(once))
    assert once == twice
