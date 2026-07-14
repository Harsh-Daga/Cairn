# Roadmap

## Opt-in rule-effect registry (future)

Cairn 1.0.1 does **not** contain a registry client, upload endpoint, telemetry, or background
network call. It only defines and produces a local, scrubbed rule-effect artifact that a user may
inspect and choose to share through their own explicit action.

The future registry vision is a community evidence base for rules that measurably reduce cost or
improve quality across agents. Any future network feature must remain opt-in, show the exact
payload before sending, preserve local operation when disabled, and accept only this allowlisted
schema:

```json
{
  "rule_text": "Read the failure output before retrying the same command.",
  "effect_metric": "waste_rate",
  "effect_size": -0.18,
  "ci": [-0.30, -0.06],
  "n_sessions": 24,
  "agent_type": "claude_code",
  "verdict": "improved"
}
```

Paths, code, repository names/identifiers, trace IDs, workspace IDs, prompts, and evidence payloads
are outside the schema and rejected. Registry aggregation would need to preserve confidence
intervals, sample sizes, agent strata, and confounded/inconclusive verdicts rather than ranking
rules by point estimate alone.
