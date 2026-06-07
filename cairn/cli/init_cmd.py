"""cairn init — scaffold a working project (§10, Phase 1)."""

from __future__ import annotations

import argparse

_SCAFFOLD: dict[str, str] = {
    "cairn.toml": """\
[project]
name = "my-cairn-project"
version = "0.1.0"

[defaults]
model = "ollama-cloud/kimi-k2.6:cloud"
params = { temperature = 0.0, max_tokens = 500 }

[sources.notes]
include = ["inputs/notes/**/*.md"]

[sources.spec]
include = ["inputs/spec.md"]

[steps.summaries]
prompt = "prompts/summarize.md"
over = "source('notes')"
output = "outputs/summaries/{{ item.stem }}.md"
materialization = "cached"

[steps.synthesis]
prompt = "prompts/synthesize.md"
inputs = ["ref('summaries')", "source('spec')"]
output = "outputs/synthesis.md"
materialization = "cached"

[steps.report]
prompt = "prompts/polish.md"
inputs = ["ref('synthesis')"]
output = "outputs/report.md"
materialization = "cached"
""",
    "inputs/spec.md": """\
# Project spec

Synthesize the note summaries into one coherent brief.
""",
    "inputs/notes/alpha.md": "# Alpha\n\nFirst note content.\n",
    "inputs/notes/beta.md": "# Beta\n\nSecond note content.\n",
    "inputs/notes/gamma.md": "# Gamma\n\nThird note content.\n",
    "prompts/summarize.md": """\
---
description: Summarize a single source document.
---
Summarize the document below in at most five bullet points.

<document path="{{ item.path }}">
{{ item.content }}
</document>
""",
    "prompts/synthesize.md": """\
---
description: Synthesize summaries with the project spec.
---
Using the summaries and spec below, write a cohesive synthesis.

{% for s in summaries %}
## {{ s.stem }}
{{ s.content }}
{% endfor %}

<spec>
{{ spec }}
</spec>
""",
    "prompts/polish.md": """\
---
description: Polish the synthesis into a final report.
---
Polish the synthesis into a concise executive report.

<synthesis>
{{ synthesis }}
</synthesis>
""",
    ".gitignore": """\
.cairn/
""",
}


def run(args: argparse.Namespace) -> int:
    root = args.dir.resolve()
    if root.exists() and any(root.iterdir()):
        print(f"refusing to init: directory not empty: {root}")
        return 1
    root.mkdir(parents=True, exist_ok=True)
    for rel, content in _SCAFFOLD.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(content, encoding="utf-8")
    print(f"Initialized Cairn project at {root}")
    print("Next: cairn validate && cairn build")
    return 0
