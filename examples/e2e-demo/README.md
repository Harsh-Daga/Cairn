# Cairn E2E demo corpus

Small git repo (3 notes + spec + prompts) for manual end-to-end testing.

## Setup

```bash
chmod +x ~/Cairn/examples/e2e-demo/setup.sh

# Default — local Ollama + llama3.2
~/Cairn/examples/e2e-demo/setup.sh ~/cairn-e2e-test

# Ollama Cloud + kimi-k2.6 (same as cairn init default)
~/Cairn/examples/e2e-demo/setup.sh ~/cairn-e2e-test --provider cloud

# Custom model string
~/Cairn/examples/e2e-demo/setup.sh ~/cairn-e2e-test --model ollama/mistral
~/Cairn/examples/e2e-demo/setup.sh ~/cairn-e2e-test --provider cloud --model kimi-k2.6:cloud
```

| `--provider` | Default model | Credentials |
|--------------|---------------|-------------|
| `local` (default) | `ollama/llama3.2` | `ollama serve`, `OLLAMA_HOST` |
| `cloud` | `ollama-cloud/kimi-k2.6:cloud` | `OLLAMA_CLOUD_API_KEY` |

Full walkthrough: [docs/guides/e2e-testing.md](../../docs/guides/e2e-testing.md).
