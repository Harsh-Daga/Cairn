#!/usr/bin/env bash
# Cairn installer — https://github.com/Harsh-Daga/Cairn
#
# Supported: macOS (Intel + Apple Silicon), Linux (x86_64, arm64, musl/glibc).
# Not supported by this script: native Windows (use WSL2 or manual install).
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/Harsh-Daga/Cairn/main/install.sh | bash
#
# Environment:
#   CAIRN_VERSION   Git tag or branch (default: main)
#   CAIRN_REPO      Git remote URL (default: https://github.com/Harsh-Daga/Cairn.git)
#   UV_INSTALL_DIR  Where to install uv (passed to Astral's installer)
#   INSTALL_UV=0    Skip uv bootstrap if already installed

set -euo pipefail

CAIRN_REPO="${CAIRN_REPO:-https://github.com/Harsh-Daga/Cairn.git}"
CAIRN_VERSION="${CAIRN_VERSION:-main}"
INSTALL_UV="${INSTALL_UV:-1}"

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m==>\033[0m %s\n' "$*"; }
err() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

OS="$(uname -s)"
ARCH="$(uname -m)"

case "${OS}" in
  Linux|Darwin) ;;
  MINGW*|MSYS*|CYGWIN*)
    err "Native Windows is not supported by this script. Use WSL2, or install manually: https://github.com/Harsh-Daga/Cairn#install"
    ;;
  *)
    err "Unsupported OS (${OS}). Use manual install: https://github.com/Harsh-Daga/Cairn#install"
    ;;
esac

info "Detected ${OS} ${ARCH}"

require_cmd() {
  local cmd="$1" hint="$2"
  command -v "${cmd}" >/dev/null 2>&1 || err "Missing required command: ${cmd}. ${hint}"
}

check_prerequisites() {
  if command -v curl >/dev/null 2>&1; then
    :
  elif command -v wget >/dev/null 2>&1; then
    warn "curl not found; wget will be used where possible"
  else
    err "Need curl or wget to download installers"
  fi
  require_cmd git "Install git (e.g. apt install git, brew install git, xcode-select --install)"
}

ensure_path() {
  local bindir="${1:-$HOME/.local/bin}"
  case ":${PATH}:" in
    *":${bindir}:"*) return 0 ;;
  esac
  warn "${bindir} is not on PATH."
  warn "Add this to your shell profile (~/.bashrc, ~/.zshrc, etc.):"
  printf '  export PATH="%s:$PATH"\n' "${bindir}"
}

install_uv() {
  if command -v uv >/dev/null 2>&1; then
    info "uv already installed ($(uv --version))"
    return 0
  fi
  if [[ "${INSTALL_UV}" != "1" ]]; then
    err "uv is required but INSTALL_UV=0 and uv was not found"
  fi
  info "Installing uv (Python toolchain manager)..."
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL https://astral.sh/uv/install.sh | sh
  else
    wget -qO- https://astral.sh/uv/install.sh | sh
  fi
  # shellcheck disable=SC1091
  if [[ -f "${HOME}/.local/bin/env" ]]; then
    # shellcheck disable=SC1091
    source "${HOME}/.local/bin/env"
  elif [[ -d "${HOME}/.local/bin" ]]; then
    export PATH="${HOME}/.local/bin:${PATH}"
  elif [[ -d "${HOME}/.cargo/bin" ]]; then
    export PATH="${HOME}/.cargo/bin:${PATH}"
  fi
  command -v uv >/dev/null 2>&1 || err "uv install finished but uv is not on PATH"
}

install_cairn() {
  local spec="git+${CAIRN_REPO}@${CAIRN_VERSION}"
  info "Installing cairn from ${spec}..."
  uv tool install cairn-workspace --from "${spec}" --force
}

verify_cairn() {
  local bindir
  bindir="$(uv tool dir --bin 2>/dev/null || true)"
  if [[ -n "${bindir}" && -d "${bindir}" ]]; then
    export PATH="${bindir}:${PATH}"
  fi
  command -v cairn >/dev/null 2>&1 || err "cairn was installed but is not on PATH"
  info "Installed $(cairn --version)"
}

main() {
  info "Cairn installer"
  check_prerequisites
  install_uv
  install_cairn
  verify_cairn
  ensure_path "$(dirname "$(command -v cairn)")"

  cat <<'EOF'

Cairn is ready. Try:

  cairn init my-project && cd my-project
  cairn validate && cairn doctor
  cairn build --yes --provider-mode recorded
  cairn help

Docs: https://github.com/Harsh-Daga/Cairn/blob/main/docs/README.md
EOF
}

main "$@"
