# Methodology

## Research question

Does an independent second-agent review detect defects in coding-agent solutions that deterministic
acceptance tests miss, and what does that additional oversight cost in time, tokens and failure modes?

Motivation: in one live run of `agent-workflow-orchestrator` (run `20260909T181636Z-62f5afc7`), a
cross-review found a Unicode lowercasing defect in a candidate that had passed its checks, and the
author fixed it in revision. That is one observation (see `docs/provenance.md`); it motivates the
question and is not evidence of a rate.

## Tasks

12 small, single-function Python tasks written for this experiment
(`experiments/coding_cross_review/tasks/`). Each has:

- `spec.md` — the contract. It **explicitly names** the edge cases that matter (Unicode case
  folding and normalization, input validation, non-mutation, boundary conditions), so a defect is a
  violation of written requirements, not of an unstated preference.
- `test_visible.py` — 3 happy-path deterministic acceptance tests. Shown to coder and reviewer.
- `test_hidden.py` — held-out tests of the spec's edge cases. **Never shown to any agent.**
- `reference.py` — used only by this repo's tests to check that the task is solvable and that both
  suites are consistent with the spec.

This mirrors a common real situation: a written spec plus an acceptance suite that covers the
main path but not every clause. The design deliberately creates room for tests to miss defects;
it measures whether review fills that gap *when such a gap exists*, not how often the gap occurs
in real projects.

Repository tests check that every reference passes both suites, that every starter fails the
visible suite, and that a known Unicode bug (`lower()` instead of `casefold()`) passes visible and
fails hidden tests.

## Episode

1. A fresh private Git repo is created with the starter and visible tests (baseline commit).
2. **Coder** (one tool-less CLI call) receives spec, starter and visible tests, and must return
   `solution.py` as exactly one fenced code block. The candidate is frozen as a commit; its diff is
   recorded.
3. **Deterministic verification**: visible and hidden suites each run in a fresh temp directory
   against the frozen file (pytest, JUnit XML, 60 s timeout).
4. If visible tests fail, the episode ends (every configuration rejects it).
5. **Independent review** (separate call, no shared context): spec, candidate, visible tests and
   their result. It returns strict JSON findings (severity, category, description, concrete failing
   input, expected result, confidence).
6. **Flag rule**, frozen in the config before the run: the candidate is *flagged* if any finding has
   severity `high` or `medium` and confidence ≥ 0.6. The rule is applied by code.
7. **Bounded revision** (config C): if flagged, the coder receives its code plus the blocking
   findings and returns one revised file, which is re-verified on both suites. No second review,
   no further rounds.

## Configurations (paired on the same coder output)

| | accepts a candidate when |
|---|---|
| A | visible tests pass |
| B | visible tests pass **and** the review does not flag it |
| C | as B; a flagged candidate gets one revision and is accepted if the revision passes visible tests |

Pairing means the A-vs-B difference is attributable to the review alone, not to coder variance.

## What counts as what

Evaluated per test-passing candidate against the hidden suite:

- **confirmed** — flagged, and hidden tests fail. Counted as a review success.
- **unconfirmed** — flagged, hidden tests pass. *Possible* false positive. It is not called a false
  positive because the hidden suite is not exhaustive; the flag may describe a real defect it misses.
- **missed** — not flagged, hidden tests fail.
- **clean approve** — not flagged, hidden tests pass.

Agreement is at the candidate level. A confirmed flag may cite a different defect from the one the
hidden tests catch; the findings are stored verbatim so this can be checked by hand, but no
finding-level labels were produced. **No human labels exist**, and no LLM-generated labels are used
as ground truth.

**Actionable**: every blocking finding includes a concrete failing input.

**Revision fixed**: hidden tests failed before revision and pass after. **Regressed**: passed before,
fail after.

## Failure classification and validity

Each call is classified (`reliability/failures.py`):

| class | kind | meaning |
|---|---|---|
| `timeout` | system | killed at the deadline |
| `cli_error` | system | non-zero exit and no usable result |
| `provider_error` / `rate_limited` | system | provider reported an error or limit |
| `malformed_output` | protocol | call succeeded, reply broke the response contract |
| `control_violation` | system | the system that ran is not the declared one |

Retryable failures get **one** retry; every attempt is kept in the episode's `calls` list and
counted. An episode whose coder or reviewer never produced valid output is `system_failure` or
`protocol_failure`, stays in the denominator and is reported separately from model outcomes.

Control checks (from `agentic-physics-bench` V2): the server-side advisor is disabled by
environment variable; each Claude call's `modelUsage` must contain only the declared model; any
`server_tool_use`, `advisor_tool_result`, native `tool_use` block or non-`message` usage iteration is
a violation. A violation stops the batch.

## Result validation

- Run directories are timestamped, include the config SHA-256 and task-file hashes, and are never
  overwritten.
- `attempts.jsonl` is written before each episode's first call.
- `python -m agent_reliability.analysis.protocol_checks <run_dir>` rebuilds every prompt from the
  recorded inputs with the same prompt builders and requires its SHA-256 to match the recorded hash.
  This shows exactly what each agent saw. It then checks that no hidden-test content appears in any
  prompt, checks every raw trace structurally for tool, server-tool and advisor blocks and for a
  single model, and checks that task and config files are unchanged since the run started.
- `python -m agent_reliability analyze <run_dir>` regenerates `metrics.json` and `summary.md` from
  `episodes.jsonl` only; no model is called. README numbers are copied from `metrics.json`.

## Run log

- Smoke run `20260927T192123Z-26ffea4d-smoke` (2 tasks: `median`, `normalize_username`): 2/2
  complete, protocol audit passed. It was used only to validate the pipeline and is excluded from
  the headline metrics.
- Full run `20260927T192610Z-26ffea4d` (12 tasks, same frozen config SHA-256 `26ffea4d…`): 12/12
  complete, audit passed. It was run once and not repeated.
- One correction was made to the audit tool (not the harness) after the smoke run. The first
  version flagged any occurrence of the string `server_tool_use`, but the CLI always emits a
  usage counter with that name (`{"web_search_requests": 0, ...}`). The check was made structural:
  a non-zero counter or a tool block fails. The in-run control check was already structural and
  had passed.

## Statistical limitations

- 12 tasks, 1 coder model, 1 reviewer model, 1 repetition in the first run. Counts are reported
  with their denominators. A task-clustered bootstrap interval is printed when there are ≥ 10 tasks;
  it describes the variability of these data, not a population rate, and with this N it is wide.
- The tasks are experimenter-written and the spec names the edge cases. Rates here say nothing about
  how often acceptance tests miss defects in real codebases.
- Cost figures are CLI-reported tokens and list-price metadata, not invoices. Latency is wall-clock
  per call, affected by provider load.
