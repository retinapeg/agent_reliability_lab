# Provenance

`agent_reliability_lab` is a new repository with its own Git history. No source repository's history,
directories or files were copied wholesale. Components were **read, then rewritten** in a smaller
form for one experiment. The three source repositories were treated as read-only inputs and were
not modified.

## Source snapshots used

Recorded before any code was written (27 September 2026):

| Source repository | Branch | Commit SHA | Working tree |
|---|---|---|---|
| `agent-workflow-orchestrator` | `main` | `f7d4a7bbcdf8d923a96c84a8554b56cf9766016d` | clean |
| `agentic-physics-bench` | `main` | `07c3689508fdb6b6471b0a73a0d00a20276cc1cc` | clean |
| `institutional-workbench` | `main` | `fa75c7028ec260d7bdf0ffbaba806f7f42c6aee6` | clean |

## agent-workflow-orchestrator → the active experiment

| Concept / file in source | Where it lives here | What changed |
|---|---|---|
| Per-engineer private Git repo cut from a frozen baseline commit; candidate frozen as a commit (`gitops.py`, `orchestrator.py`) | `environments/coding/environment.py` `Workspace` | Rewritten in ~30 lines: one engineer, one file, `git init` + baseline commit + candidate commit + recorded diff. No worktree pool, bundle export or integration. |
| Checks run on the frozen commit in a *fresh* checkout, never in the agent's workspace (`evaluator.py`) | `verifiers/pytest_verifier.py` | Rewritten: copies the frozen `solution.py` and one test file into a fresh temp dir, runs pytest with a timeout, parses JUnit XML. No benchmark/scoring layer. |
| Implement → cross-review → bounded revision → re-evaluation loop (`orchestrator.py`) | `runners/cross_review.py` | Reduced to one coder and one independent reviewer per task, at most one revision. The two-engineer competition and winner selection were dropped. |
| Review schema: severity, reproduction, violated requirement, confidence 0–1; malformed review = failed review (`prompts/review.md`, `models.py`, `test_review_and_judge_validation.py`) | `review/reviewer.py` | Rewritten with a fixed category list and an explicit, config-frozen flag rule applied by code. |
| Sanitized child environment for CLI agents (`providers/cli.py`) | `agents/cli_agent.py` `sanitized_env` | Allow-list of a few variables plus the advisor switch. |
| Scripted offline provider (`providers/scripted.py`) | `agents/cli_agent.py` `ScriptedAgent` | Minimal: replies per role, `None` simulates a provider failure. |
| "Deterministic gates decide; model output cannot rescue a failing candidate" | Configuration A/B/C definitions | Kept as a principle: review can only *reject* a test-passing candidate, never accept a failing one. |
| Motivating observation (VALIDATION.md, live run `20260909T181636Z-62f5afc7`) | README, methodology | Cited, not reproduced. See below. |

**Deliberately not imported:** the `team` CLI and `team.toml` loader, adaptive Hackathon/Engineering
modes, planner/scope verdicts, the judge, scoring (`Decimal` 0–10,000), manifest/bundle export,
integration into a source repo, API providers (OpenAI Responses / Anthropic Messages whole-file
operations), deadlines/cancellation machinery, prompt templating module, skills.

### The Unicode observation — what is and is not verifiable

`agent-workflow-orchestrator/VALIDATION.md` (lines 72–77 at the SHA above) records, for live run
`20260909T181636Z-62f5afc7`: both final candidates passed the required test and demo gate, and
*"The Codex review found a real Unicode lowercasing edge case in Claude's initial implementation;
Claude accepted and fixed it during revision."* The same file states the raw audit archive for that
run is **not** in the repository. So this is a single documented observation, verifiable only as a
written record. I did not find a statement of how many deterministic acceptance tests the initial
candidate passed, so this repository does not repeat any specific test count. It motivates the
experiment; no rate is derived from it.

## agentic-physics-bench → validity, traces, provenance (frozen study; not modified, not re-analysed)

| Concept / file in source | Where it lives here | What changed |
|---|---|---|
| Server-side advisor can add a second model to a "tool-less" CLI call; disable via `CLAUDE_CODE_DISABLE_ADVISOR_TOOL=1` and check every call (`run_v2.py` `ENV_CONTROLS`, `v2_control_violations`, `summarize_call`) | `agents/cli_agent.py` `_ENV_CONTROLS`, `summarize_claude_events`; `reliability/failures.py` `claude_control_violations` | Adapted: model check accepts an alias (`haiku`, `sonnet`) instead of an exact ID; checks `modelUsage` keys, `advisor_tool_result`/`server_tool_use` blocks, native `tool_use` blocks and non-`message` usage iterations. |
| Isolated CLI argv: `--tools ""`, `--safe-mode`, `--strict-mcp-config`, `--no-session-persistence`, `stream-json` in an empty temp dir (`models.py`) | `ClaudeCliAgent.argv` | Same flags, plus an explicit empty MCP config (from institutional-workbench). |
| A control violation invalidates the episode, keeps it in the denominator and stops the batch | `runners/cross_review.py` `BatchStopped`, `cli.py` | Same rule. |
| Attempt record written before the first model call; append-only episode JSONL; raw event streams gitignored, reviewed summaries committed; path redaction (`run_v2.py`) | `traces/store.py` | Rewritten; run directories are refused if they already exist. |
| Development vs evaluation separation; answer keys never shown to the model | Visible vs hidden test suites | Adapted: hidden tests play the role of held-out answer keys. |
| Counts with denominators first; cluster bootstrap only as description; "what these results do not show" section (`analyze_v2.py`, README) | `analysis/summarize.py`, `results/latest_summary.md` | Rewritten for this experiment. |

**Deliberately not imported:** physics tasks and generators, the `fit_line` tool, V1/V2 prompts,
freeze-manifest hashing of the whole harness (replaced by config + task-file hashes in `run.json`),
charts, and all historical results. The physics results are not regenerated or reinterpreted here.

## institutional-workbench → measurement integrity

| Concept / file in source | Where it lives here | What changed |
|---|---|---|
| One structured response contract per call; malformed output is a failure, not a guess (`providers.py`) | `extract_solution` (exactly one fenced block), `parse_review` (strict JSON) | Adapted: IW blocks with no retry; here malformed output gets **one counted retry**, then the episode is a `protocol_failure`. |
| Unsuccessful Claude envelope (`is_error`, `subtype != success`) vs Codex failed turn vs Codex tool attempt (`providers.py`) | `reliability/failures.py` `classify_claude_call`, `classify_codex_events` | Rewritten as pure functions with an explicit taxonomy: `timeout`, `cli_error`, `provider_error`, `rate_limited`, `malformed_output`, `control_violation`. |
| Codex read-only argv with tool features disabled (`providers.py`) | `CodexCliAgent.argv` | Copied flag list; available but not used in the first run's config. |
| Timeouts as first-class outcomes (`runner.py`) | `_run` in `cli_agent.py`, verifier timeout | Simplified to `subprocess.run(timeout=...)`. |

**Deliberately not imported:** the specialist/decision/QA pipeline, pydantic models, repository
snapshotting, patch delivery, the `inst` CLI, cancel files and run budgets.

## New in this repository (no source counterpart)

- The 12 coding tasks, their visible and hidden test suites and reference solutions
  (`experiments/coding_cross_review/tasks/`), written for this experiment.
- The A/B/C paired evaluation and the confirmed/unconfirmed/missed outcome scheme.
- `analysis/summarize.py` metrics and the generated `results/latest_summary.md`.
