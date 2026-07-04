"""Phase T — scrub + fleet export tests."""

from __future__ import annotations

from pathlib import Path

from cairn.render.scrub import scrub_path, scrub_text


def test_scrub_redacts_secrets() -> None:
    assert "[REDACTED]" in scrub_text("api_key=sk-abcdefghijklmnopqrstuvwxyz123456")


def test_scrub_redacts_home_paths() -> None:
    out = scrub_path("/Users/alice/project/secret.py")
    assert "/Users/alice" not in out
    assert "[REDACTED]" in out


def test_export_bundle_manifest(tmp_path: Path) -> None:
    from cairn.fleet.export import export_bundle
    from cairn.ingest.parsers.claude_code import parse_jsonl_file
    from cairn.ingest.writer import CaptureWriter

    fixture = Path(__file__).parent / "fixtures" / "ingest" / "claude_code_mini.jsonl"
    root = tmp_path / "proj"
    root.mkdir()
    parsed = parse_jsonl_file(fixture, repo_root=root)
    assert parsed is not None
    writer = CaptureWriter(root)
    try:
        writer.ingest_claude_session(parsed)
    finally:
        writer.close()

    out = tmp_path / "bundle.cairn"
    result = export_bundle(root, out, with_snippets=False)
    assert out.is_file()
    assert "text_inline stripped" in " ".join(result.get("manifest", []))
