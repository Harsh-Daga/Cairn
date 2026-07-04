#!/usr/bin/env bash
# Copy the E2E demo repo to a fresh directory and init git.
#
# Usage:
#   ./examples/e2e-demo/setup.sh [DEST] [OPTIONS]
#
# Options (default: local Ollama + llama3.2):
#   --provider local|cloud   Preset provider (default: local)
#   --model <name>           Model id or full provider/model string
#
# Environment (override flags):
#   CAIRN_E2E_PROVIDER=local|cloud
#   CAIRN_E2E_MODEL=<model>
#
# Examples:
#   ./setup.sh ~/cairn-e2e-test
#   ./setup.sh ~/cairn-e2e-test --provider cloud
#   ./setup.sh ~/cairn-e2e-test --model ollama-cloud/kimi-k2.6:cloud
#   ./setup.sh ~/cairn-e2e-test --provider local --model llama3.2

set -euo pipefail

PROVIDER="${CAIRN_E2E_PROVIDER:-local}"
MODEL="${CAIRN_E2E_MODEL:-}"
DEST=""

usage() {
  sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --provider)
      PROVIDER="${2:?--provider requires local or cloud}"
      shift 2
      ;;
    --model)
      MODEL="${2:?--model requires a value}"
      shift 2
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "error: unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
    *)
      if [[ -z "$DEST" ]]; then
        DEST="$1"
        shift
      else
        echo "error: unexpected argument: $1" >&2
        usage >&2
        exit 1
      fi
      ;;
  esac
done

DEST="${DEST:-$HOME/cairn-e2e-test}"
SRC="$(cd "$(dirname "$0")" && pwd)"

case "$PROVIDER" in
  local|ollama)
    DEFAULT_MODEL="ollama/llama3.2"
    SETUP_NOTE="local Ollama (ollama serve + ollama pull llama3.2)"
    ;;
  cloud|ollama-cloud)
    DEFAULT_MODEL="ollama-cloud/kimi-k2.6:cloud"
    SETUP_NOTE="Ollama Cloud (export OLLAMA_CLOUD_API_KEY=...)"
    PROVIDER="cloud"
    ;;
  *)
    echo "error: --provider must be local or cloud (got: $PROVIDER)" >&2
    exit 1
    ;;
esac

resolve_model() {
  local raw="${1:-$DEFAULT_MODEL}"
  if [[ "$raw" == */* ]]; then
    echo "$raw"
    return
  fi
  case "$PROVIDER" in
    cloud) echo "ollama-cloud/$raw" ;;
    local) echo "ollama/$raw" ;;
  esac
}

RESOLVED_MODEL="$(resolve_model "$MODEL")"

if [[ -e "$DEST" ]] && [[ -n "$(ls -A "$DEST" 2>/dev/null)" ]]; then
  echo "error: destination not empty: $DEST" >&2
  exit 1
fi

mkdir -p "$DEST"
cp -R "$SRC"/. "$DEST/"
rm -f "$DEST/setup.sh"

python3 - "$DEST/cairn.toml" "$RESOLVED_MODEL" "$SETUP_NOTE" "$PROVIDER" <<'PY'
import re
import sys
from pathlib import Path

path, model, note, provider = sys.argv[1:5]
max_tokens = 4096 if provider == "cloud" else 1024
text = Path(path).read_text()
lines = text.splitlines()
out: list[str] = []
for line in lines:
    if line.startswith("# E2E demo project"):
        out.append(f"# E2E demo project — {note}")
        continue
    if line.startswith("# Requires:"):
        continue
    if line.strip().startswith("model = "):
        out.append(f'model = "{model}"')
        continue
    if line.strip().startswith("params = "):
        out.append(f"params = {{ temperature = 0.2, max_tokens = {max_tokens} }}")
        continue
    out.append(line)
Path(path).write_text("\n".join(out) + "\n")
PY

cd "$DEST"
git init -q
git add .
git commit -q -m "Initial E2E demo corpus" || true

echo "Created $DEST"
echo "  provider preset: $PROVIDER"
echo "  model: $RESOLVED_MODEL"
echo ""
echo "Next:"
echo "  cd $DEST"
if [[ "$PROVIDER" == "cloud" ]]; then
  echo "  export OLLAMA_CLOUD_API_KEY='your-key'"
  echo "  cairn doctor && cairn build --yes --provider-mode live"
else
  echo "  ollama serve    # separate terminal"
  echo "  ollama pull llama3.2"
  echo "  export OLLAMA_HOST=http://127.0.0.1:11434"
  echo "  cairn doctor && cairn build --yes --provider-mode live"
fi
