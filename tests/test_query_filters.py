from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from server.query_filters import parse_filter


def test_filter_parser_supports_quotes_escaping_comparisons_and_dates() -> None:
    parsed = parse_filter(
        r'"user request" file:"src/my file.py" tool:read cost:>=1.25 after:2026-07-01'
    )

    assert parsed.valid
    assert parsed.phrase == "user request"
    assert [(token.field, token.value, token.comparison) for token in parsed.tokens] == [
        ("file", "src/my file.py", "eq"),
        ("tool", "read", "eq"),
        ("cost", "1.25", "gte"),
        ("after", "2026-07-01", "eq"),
    ]


def test_filter_parser_returns_actionable_errors_without_broadening_query() -> None:
    parsed = parse_filter(
        'unknown:value cost:many after:yesterday corrected:maybe claim:unsupported "unterminated'
    )

    assert not parsed.valid
    assert "Invalid quoting" in parsed.errors[0].message
    assert parsed.tokens == ()

    parsed = parse_filter(
        "unknown:value cost:many after:yesterday corrected:maybe claim:unsupported"
    )
    assert not parsed.valid
    assert {error.token for error in parsed.errors} == {
        "unknown:value",
        "cost:many",
        "after:yesterday",
        "corrected:maybe",
        "claim:unsupported",
    }
    assert parsed.values("claim")[0].available is False


def test_is_error_remains_a_compatible_status_alias() -> None:
    parsed = parse_filter("is:error")

    assert parsed.valid
    assert parsed.tokens[0].field == "status"
    assert parsed.tokens[0].value == "error"


@given(st.text(max_size=600))
def test_filter_parser_never_executes_or_crashes_on_arbitrary_text(raw: str) -> None:
    parsed = parse_filter(raw)

    assert parsed.raw == raw
    assert all(token.raw in raw for token in parsed.tokens)
    if len(raw) > 500:
        assert not parsed.valid
