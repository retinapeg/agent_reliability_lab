## Codex smoke setup

- The tool-loop commits are pushed.
- The reviewer is pinned to claude-sonnet-5, so only the coder changes from v1.
- gpt-6-sol runs at hard-coded medium effort, so the results compare coders, not providers.
- The Codex model is declared, not read from usage.
- The tool loop has only been run live with claude_cli.

## 2026-10-03 20:41 UTC — agent_arena run: codex-smoke
- ran: claude (claude-sonnet-5) on codex-smoke.md; run 20261003T204130Z-codex-smoke-49dac0
- result: 3 PASS, 0 FAIL, 6 UNKNOWN; verified=False; est. cost null
- next: resolve UNKNOWN check 'log has no BATCH STOPPED': /tmp/codex-smoke.log not found

## 2026-10-03 21:14 UTC — agent_arena run: codex-smoke
- ran: claude (claude-sonnet-5) on codex-smoke.md; run 20261003T211118Z-codex-smoke-824939
- result: 9 PASS, 0 FAIL, 0 UNKNOWN; verified=True; est. cost null
- next: run the full v2 Codex batch and compare coders against v1

## 2026-10-03 — costs derived from tokens; no more $0.0000 for unreported cost
- fixed: `compute_metrics()` started every role's cost at 0.0, so Codex roles (no CLI cost)
  were summarised as $0.0000. Costs are now derived per call at analysis time:
  `cli_reported` if the CLI gave one, else `api_estimate` from tokens and the price table, else
  `unpriced` (null). Roles print "$X (k/n calls priced)" or "not reported".
- added: `src/agent_reliability/pricing.py` (identical to the orchestrator's), reading
  `$AGENT_PRICING_FILE` or `~/.agent-arena/pricing.toml`; a Claude cross-check line (CLI-reported
  vs API estimate for the same calls); the 5m/1h cache-write split is now kept in Claude usage;
  `tests/test_costs.py` (6 tests); 69 pass. Ruff: 38 findings, the same as before this change.
- re-ran the summary for 20261003T211124Z-99cc8e25-codex-smoke: coder $0.0933 (6/6 calls
  priced); review + revision $0.1643 (9/9). Cross-check: CLI $0.1100 vs estimate $0.0958
  (−12.9%), because this run's episodes predate the 5m/1h split; priced from the raw traces
  with the 1h rate the estimate is $0.1100 (gap 0.0%).
- changed metrics keys: `overhead.coder_list_cost_usd` / `oversight_list_cost_usd` are replaced
  by `overhead.coder_cost` / `oversight_cost` ({cost_usd, calls_priced, calls}). The tracked
  metrics.json and summary.md of older runs were not regenerated.
- not verified: a live run with the new code (no model calls were made).
- next: regenerate the tracked summaries if the README numbers should use the new cost lines.

## 2026-10-03 — review fixes: long-context rule, .claude/ ignored
- `src/agent_reliability/pricing.py` re-synced with the orchestrator: the >272K long-context
  rates apply only to a record marked as a single request. Lab call records are totals of one
  CLI invocation, so they are priced at base rates and marked "long context unknown" when over
  the limit. No figure for the codex-smoke run changed (largest record is far below 272K).
- `.claude/` added to .gitignore. 69 tests pass; ruff findings unchanged at 38 (pre-existing).
