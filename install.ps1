# Cairn installer for Windows (PowerShell)
# Usage: irm https://raw.githubusercontent.com/Harsh-Daga/Cairn/main/install.ps1 | iex
#
# Environment:
#   $env:CAIRN_VERSION = "4.0.0"   Pin PyPI version
#   $env:INSTALL_UV = "0"            Skip uv bootstrap

$ErrorActionPreference = "Stop"

$CairnVersion = if ($env:CAIRN_VERSION) { $env:CAIRN_VERSION } else { "" }
$InstallUv = if ($env:INSTALL_UV) { $env:INSTALL_UV } else { "1" }

Write-Host "==> Cairn installer (Windows)" -ForegroundColor Cyan

function Ensure-Uv {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Write-Host "==> uv already installed ($((uv --version)))" -ForegroundColor Cyan
        return
    }
    if ($InstallUv -ne "1") {
        throw "uv is required but INSTALL_UV=0 and uv was not found"
    }
    Write-Host "==> Installing uv..." -ForegroundColor Cyan
    irm https://astral.sh/uv/install.ps1 | iex
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw "uv install finished but uv is not on PATH"
    }
}

function Ensure-Path {
    $bindir = uv tool dir --bin 2>$null
    if ($bindir -and (Test-Path $bindir)) {
        $env:Path = "$bindir;$env:Path"
    }
}

function Install-Cairn {
    $spec = "cairn-workspace"
    if ($CairnVersion) {
        $spec = "cairn-workspace==$CairnVersion"
    }

    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Write-Host "==> Installing $spec via uv tool..." -ForegroundColor Cyan
        uv tool install --upgrade $spec
        return
    }
    if (Get-Command pipx -ErrorAction SilentlyContinue) {
        Write-Host "==> Installing $spec via pipx..." -ForegroundColor Cyan
        pipx install --force $spec
        return
    }
    if (Get-Command pip -ErrorAction SilentlyContinue) {
        Write-Host "==> Installing $spec via pip --user..." -ForegroundColor Cyan
        pip install --user --upgrade $spec
        return
    }
    throw "No installer found. Install uv: irm https://astral.sh/uv/install.ps1 | iex"
}

Ensure-Uv
Install-Cairn
Ensure-Path

if (Get-Command cairn -ErrorAction SilentlyContinue) {
    cairn --version
    cairn doctor
} else {
    Write-Warning "~\.local\bin may not be on PATH"
}

Write-Host @"

Cairn is ready:

  cd <your-repo>; cairn

No account, no cloud, no config. Stop with: cairn stop
Docs: https://github.com/Harsh-Daga/Cairn
"@
