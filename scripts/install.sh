#!/bin/sh
# Cairn installer — POSIX sh, idempotent.
#
# Downloaded-script install:
#   curl -LsSf URL -o /tmp/cairn-install.sh && sh /tmp/cairn-install.sh
#
# Environment:
#   INSTALL_UV=0      Skip uv bootstrap (error if uv is absent)
#   CAIRN_VERSION=x   Pin PyPI version (default: latest)

set -eu

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m==>\033[0m %s\n' "$*"; }
err() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

INSTALL_UV="${INSTALL_UV:-1}"
CAIRN_VERSION="${CAIRN_VERSION:-}"

install_uv() {
  if command -v uv >/dev/null 2>&1; then
    info "uv already installed ($(uv --version))"
    return 0
  fi
  if [ "${INSTALL_UV}" != "1" ]; then
    err "uv is required but INSTALL_UV=0 and uv was not found"
  fi
  info "Installing uv..."
  installer="$(mktemp "${TMPDIR:-/tmp}/cairn-uv-install.XXXXXX")"
  trap 'rm -f "${installer:-}"' EXIT HUP INT TERM
  if command -v curl >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh -o "${installer}"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "${installer}" https://astral.sh/uv/install.sh
  else
    err "Need curl or wget to download the uv installer"
  fi
  sh "${installer}"
  rm -f "${installer}"
  trap - EXIT HUP INT TERM
  if [ -f "${HOME}/.local/bin/env" ]; then
    # shellcheck disable=SC1091
    . "${HOME}/.local/bin/env"
  elif [ -d "${HOME}/.local/bin" ]; then
    PATH="${HOME}/.local/bin:${PATH}"
    export PATH
  fi
  command -v uv >/dev/null 2>&1 || err "uv install finished but uv is not on PATH"
}

ensure_path() {
  bindir="$(uv tool dir --bin 2>/dev/null || true)"
  [ -n "${bindir}" ] && [ -d "${bindir}" ] && PATH="${bindir}:${PATH}" && export PATH
  case ":${PATH}:" in
    *":${bindir}:"*) ;;
    *)
      if [ -n "${bindir}" ]; then
        warn "${bindir} is not on PATH. Add to your shell profile:"
        printf '  export PATH="%s:$PATH"\n' "${bindir}"
      fi
      ;;
  esac
}

install_cairn() {
  spec="cairn-workspace"
  if [ -n "${CAIRN_VERSION}" ]; then
    spec="cairn-workspace==${CAIRN_VERSION}"
  fi

  if command -v uv >/dev/null 2>&1; then
    info "Installing ${spec} via uv tool..."
    uv tool install --upgrade "${spec}"
    return 0
  fi

  if command -v pipx >/dev/null 2>&1; then
    info "Installing ${spec} via pipx..."
    pipx install --force "${spec}"
    return 0
  fi

  if command -v pip3 >/dev/null 2>&1; then
    info "Installing ${spec} via pip --user..."
    pip3 install --user --upgrade "${spec}"
    return 0
  fi

  err "No installer found. Install uv from https://docs.astral.sh/uv/"
}

main() {
  info "Cairn installer"
  if ! command -v uv >/dev/null 2>&1; then
    install_uv
  fi
  install_cairn
  ensure_path

  if command -v cairn >/dev/null 2>&1; then
    info "Installed $(cairn --version)"
    cairn doctor
  fi

  cat <<'EOF'

Cairn is ready:

  cd <your-repo> && cairn

No account, no cloud, no config. Stop with: cairn stop
Docs: https://github.com/Harsh-Daga/Cairn
EOF
}

main "$@"
