# Cairn installer for Windows (PowerShell)
# Usage: irm https://raw.githubusercontent.com/Harsh-Daga/Cairn/main/install.ps1 | iex

$ErrorActionPreference = "Stop"

$CairnRepo = if ($env:CAIRN_REPO) { $env:CAIRN_REPO } else { "https://github.com/Harsh-Daga/Cairn.git" }
$CairnVersion = if ($env:CAIRN_VERSION) { $env:CAIRN_VERSION } else { "main" }

Write-Host "==> Cairn installer (Windows)" -ForegroundColor Cyan

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Error "git is required. Install Git for Windows: https://git-scm.com/download/win"
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "==> Installing uv..." -ForegroundColor Cyan
    irm https://astral.sh/uv/install.ps1 | iex
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "uv install finished but uv is not on PATH. Add %USERPROFILE%\.local\bin to PATH."
}

$spec = "git+${CairnRepo}@${CairnVersion}"
Write-Host "==> Installing cairn from $spec" -ForegroundColor Cyan
uv tool install cairn-workspace --from $spec --force

if (-not (Get-Command cairn -ErrorAction SilentlyContinue)) {
    Write-Warning "~\.local\bin may not be on PATH. Add it to your user PATH environment variable."
}

cairn --version

Write-Host @"

Cairn is ready. Try:

  cairn init my-project
  cd my-project
  cairn validate
  cairn build --yes --provider-mode recorded

PyPI:  pip install cairn-workspace  (https://pypi.org/project/cairn-workspace/)
Docs:  https://github.com/Harsh-Daga/Cairn/blob/main/docs/README.md
"@
