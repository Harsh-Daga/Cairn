# Weekly recap

`GET /api/recap`, UI `/recap`, and `cairn recap` summarize a **rolling 7-day UTC** window ending
at generation time. The response exposes `period_start`, `period_end`, `timezone`, and
`period_kind=rolling_7d` so consumers do not guess the bounds.

## Contents

- Spend and estimated avoidable spend with top causes
- Quality and cost-per-success trends vs the prior seven days
- Best/worst sessions by cost with privacy-safe titles
- Experiment verdicts and descriptive decayed rules
- Guard instruction-file events (listed, not treated as causal)
- One recommended action when evidence exists
- Explicit limitations when data is thin

`cairn recap --share` still writes a private local PNG share card.

## Local scheduling

Recap is local-only. Schedule `cairn recap` (or `cairn recap --share`) with your OS tools:

### cron (Linux / macOS)

```cron
0 9 * * 1 cd /path/to/repo && cairn recap --share
```

### launchd (macOS)

Save `~/Library/LaunchAgents/com.cairn.recap.plist` with a `StartCalendarInterval` for Monday
morning and `ProgramArguments` of `["/path/to/cairn", "recap", "--share"]`, then:

```bash
launchctl load ~/Library/LaunchAgents/com.cairn.recap.plist
```

### Windows Task Scheduler

```powershell
schtasks /Create /SC WEEKLY /D MON /ST 09:00 /TN "CairnRecap" /TR "cairn recap --share"
```

Point each scheduler at the workspace that owns `.cairn/` (or pass `--workspace`).
