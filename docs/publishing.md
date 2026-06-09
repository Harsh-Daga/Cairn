# Publishing to PyPI

Cairn publishes to PyPI as **`cairn-workspace`** (the `cairn` name is taken). The CLI
command remains `cairn`.

## Trusted publishing setup

1. On [PyPI → Publishing](https://pypi.org/manage/account/publishing/), add a trusted publisher:

   | Field | Value |
   |-------|--------|
   | PyPI Project Name | `cairn-workspace` |
   | Owner | `Harsh-Daga` |
   | Repository name | `Cairn` |
   | Workflow name | `publish.yml` |
   | Environment name | `pypi` |

2. On GitHub → **Harsh-Daga/Cairn** → Settings → Environments, create **`pypi`**.

3. Create a GitHub Release (e.g. tag `v1.1.0`). The [publish workflow](../.github/workflows/publish.yml)
   runs on `release: published` and uploads the wheel + sdist via OIDC (no API token).

## Manual publish (maintainers)

```bash
uv build
uv publish   # requires PyPI token or trusted publishing context
```

## Install for users

```bash
uv tool install cairn-workspace
cairn --version
```
