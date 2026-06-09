"""Tests for v1.1 completion items."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from cairn.agents.profiles import check_profile
from cairn.doctor.checks import run_doctor
from cairn.doctor.mcp import check_mcp_server, load_mcp_servers
from cairn.graph.builder import build_graph, enumerate_step_outputs
from cairn.ingest.live.install import install_live, live_install_status, uninstall_live
from cairn.loader.toml import load_project


def test_map_over_ref_builds_nodes(project_dir: Path) -> None:
    toml = project_dir / "cairn.toml"
    toml.write_text(
        toml.read_text(encoding="utf-8")
        + """
[steps.repolish]
prompt = "prompts/summarize.md"
over = "ref('summaries')"
output = "outputs/repolished/{{ item.stem }}.md"
""",
        encoding="utf-8",
    )
    project = load_project(project_dir)
    upstream = enumerate_step_outputs(project, "summaries")
    assert len(upstream) == 3
    graph = build_graph(project)
    repolish = [n for n in graph.nodes if n.step == "repolish"]
    assert len(repolish) == 3
    assert all(n.kind == "map" for n in repolish)
    assert {n.output_path for n in repolish} == {
        "outputs/repolished/alpha.md",
        "outputs/repolished/beta.md",
        "outputs/repolished/gamma.md",
    }


def test_doctor_checks_mcp_and_agent_profiles(
    project_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OLLAMA_CLOUD_API_KEY", "test-key")
    toml = project_dir / "cairn.toml"
    toml.write_text(
        toml.read_text(encoding="utf-8")
        + """
[agents]
profiles = ["generic"]

[mcp.servers.docs]
transport = "stdio"
command = "python3"
args = ["-c", "pass"]
"""
    )
    project = load_project(project_dir)
    servers = load_mcp_servers(project_dir)
    assert len(servers) == 1
    ok, _ = check_mcp_server(servers[0])
    assert ok
    report = run_doctor(project)
    assert any("mcp server" in i.message for i in report.issues)
    assert any("agent profile" in i.message for i in report.issues)


def test_agent_profile_missing_binary() -> None:
    ok, message = check_profile("claude-code")
    if shutil.which("claude"):
        assert ok
    else:
        assert not ok
        assert "claude" in message


def test_live_install_records_tail_watchers(project_dir: Path) -> None:
    status = install_live(project_dir, source="all")
    assert "cursor" in status.tail_watchers
    assert "hermes" in status.tail_watchers
    current = live_install_status(project_dir)
    assert current is not None
    assert current.tail_watchers == status.tail_watchers
    assert uninstall_live(project_dir)


def test_benchmark_thresholds(tmp_path: Path) -> None:
    from cairn.cache.cas import ContentAddressableStore
    from cairn.graph.session_graph import build_session_graph
    from cairn.performance.bench import benchmark_cas_reads, benchmark_graph_layout

    cas = ContentAddressableStore(tmp_path)
    digest = cas.put(b"bench")
    assert benchmark_cas_reads(tmp_path, digest, iterations=20) < 0.05
    graph = build_session_graph([{"seq": 1, "type": "user_prompt"}])
    assert benchmark_graph_layout(graph, iterations=10) < 0.05
