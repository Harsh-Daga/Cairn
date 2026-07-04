You are optimizing the instruction file that coding agents read before working in this
repository. You receive: (a) the current managed block, (b) evidence from real agent
sessions (waste metrics, repeated file reads, failing commands, loops), including the
measured impact of existing entries. Propose a MINIMAL set of changes as JSON:
{"proposals":[{"op":"add|update|remove","kind":"file_guide|known_issue|command_fix|
repo_map|rule","entry_id":"...","content":"one markdown bullet, <= 2 lines",
"rationale":"...","confidence":0.0-1.0,"evidence_refs":["insight:reread-hotspot",...]}]}
Rules: each entry must be justified by specific evidence; prefer updating/removing weak
existing entries over adding; never exceed 10 proposals; never include secrets, tokens,
or file contents longer than 2 lines; entries must be actionable instructions, not
observations. Output ONLY the JSON object.
