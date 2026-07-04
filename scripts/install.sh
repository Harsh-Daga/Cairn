#!/bin/sh
# Cairn installer — https://cairn.dev
#
# One line to a dashboard of your coding-agent history:
#   curl -LsSf https://cairn.dev/install.sh | sh
#
# POSIX sh. Installs uv (if missing), then installs/upgrades cairn-workspace as a
# uv tool. Writes nothing outside uv's tool dir. Re-running is idempotent.
#
# Environment:
#   INSTALL_UV=0   Skip uv bootstrap (error if uv is absent)

set -eu

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m==>\033[0m %s\n' "$*"; }
err() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

INSTALL_UV="${INSTALL_UV:-1}"

install_uv() {
  if command -v uv >/dev/null 2>&1; then
    info "uv already installed ($(uv --version))"
    return 0
  fi
  if [ "${INSTALL_UV}" != "1" ]; then
    err "uv is required but INSTALL_UV=0 and uv was not found"
  fi
  info "Installing uv (Python toolchain manager)..."
  if command -v curl >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- https://astral.sh/uv/install.sh | sh
  else
    err "Need curl or wget to download the uv installer"
  fi
  # Make uv visible on PATH for the rest of this script.
  if [ -f "${HOME}/.local/bin/env" ]; then
    # shellcheck disable=SC1091
    . "${HOME}/.local/bin/env"
  elif [ -d "${HOME}/.local/bin" ]; then
    PATH="${HOME}/.local/bin:${PATH}"
    export PATH
  fi
  command -v uv >/dev/null 2>&1 || err "uv install finished but uv is not on PATH"
}

install_cairn() {
  info "Installing cairn-workspace..."
  uv tool install --upgrade cairn-workspace
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

main() {
  info "Cairn installer"
  install_uv
  install_cairn
  ensure_path
  if command -v cairn >/dev/null 2>&1; then
    info "Installed $(cairn --version)"
  fi

  cat <<'EOF'

Cairn is ready. Next step:

  cd <repo> && cairn

That mines your existing agent history and opens a dashboard in under 60 seconds.
Try it without installing anything:  uvx cairn-workspace

Docs:  https://cairn.dev/docs
EOF
}

main "$@"
