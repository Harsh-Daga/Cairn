# Python SDK

Cairn exposes a stable Python API from the `cairn` package (SemVer from 1.0).

## Install

The SDK ships with the CLI ([PyPI](https://pypi.org/project/cairn-workspace/)):

```bash
pip install cairn-workspace
```

For library use in another project:

```bash
pip install cairn-workspace
# or with uv:
uv add cairn-workspace
# or from git:
uv add "cairn-workspace @ git+https://github.com/Harsh-Daga/Cairn.git"
```

## Open a project

```python
import cairn

project = cairn.Project.open("/path/to/my-project")
print(project.name, project.root)
```

`Project.open` resolves the project root and loads `cairn.toml` when present.

## Run a workflow

```python
from cairn.workflow import run as workflow_run

run = workflow_run(
    project=project,
    yes=True,
    provider_mode="recorded",  # or "live"
)
print(run.run_id, run.kind, run.workflow_ref)
```

`run` is a `cairn.Run` with `kind="provider"` for pipeline executions.

## Render and report

```python
from cairn.render import html, report_json

report = report_json(run)
assert report["kind"] == "provider"

index = html(run, output=project.root / "outputs" / "bundle")
print(index)  # Path to index.html
```

For capture sessions, construct a `Run` with `kind="capture"` and `session_id`:

```python
from cairn.sdk.project import Run

run = Run(
    project_root=project.root,
    run_id="<ledger-run-id>",
    kind="capture",
    session_id="sess-…",
)
report_json(run)
html(run, output=project.root / "outputs" / "capture-bundle")
```

## Capture ingest (library)

```python
from cairn.ingest.parsers.claude_code import parse_jsonl_file
from cairn.ingest.writer import CaptureWriter

parsed = parse_jsonl_file(path_to_jsonl, repo_root=project.root)
writer = CaptureWriter(project.root)
try:
    result = writer.ingest_claude_session(parsed)
finally:
    writer.close()
print(result.session_id, result.run_id)
```

Agent parsers and the writer API are public for integrators building custom ingest paths.

## Version

```python
import cairn
print(cairn.__version__)
```

## HTTP API alternative

If you prefer REST over embedded Python, run `cairn api serve` and use the [HTTP API](api.md).

## E2E verification

```bash
cd ~/cairn-e2e-test
python3 << 'PY'
import cairn
from cairn.workflow import run as workflow_run
from cairn.render import html, report_json

project = cairn.Project.open(".")
run = workflow_run(project=project, yes=True, provider_mode="recorded")
print("kind:", report_json(run)["kind"])
html(run, output=project.root / "outputs" / "sdk-bundle")
print("Wrote outputs/sdk-bundle/index.html")
PY
```
OpenAPI spec at `/v1/openapi.json`.
