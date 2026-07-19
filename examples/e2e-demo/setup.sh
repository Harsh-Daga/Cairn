#!/usr/bin/env bash
# Prepare a disposable workspace with the e2e-demo sample config.
#
# Usage:
#   ./examples/e2e-demo/setup.sh [DEST]
#
# This does not call a model provider. Prefer `cairn demo --reset` for the
# deterministic fixture used in CI and the public Pages snapshot.

set -euo pipefail

DEST="${1:-$HOME/cairn-e2e-demo}"
SRC="$(cd "$(dirname "$0")" && pwd)"

if [[ -e "$DEST" ]] && [[ -n "$(ls -A "$DEST" 2>/dev/null || true)" ]]; then
  echo "error: destination not empty: $DEST" >&2
  exit 1
fi

mkdir -p "$DEST/.cairn"
cp "$SRC/cairn.toml" "$DEST/.cairn/config.toml"
cp "$SRC/README.md" "$DEST/README.md"
printf '%s\n' ".cairn/" >"$DEST/.gitignore"

cd "$DEST"
git init -q
git add .
git commit -q -m "Cairn e2e-demo workspace skeleton" || true

echo "Created $DEST"
echo ""
echo "Deterministic path (recommended):"
echo "  cairn demo --reset"
echo "  cairn ui --workspace \"\$HOME/.cairn-demo\""
echo "  cairn check --workspace \"\$HOME/.cairn-demo\""
echo ""
echo "Or sync this workspace after installing an agent adapter:"
echo "  cd $DEST && cairn sync && cairn doctor && cairn check"
