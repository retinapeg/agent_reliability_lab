# Agent Reliability Lab

Does an independent model review catch coding defects that deterministic acceptance tests miss, and what does that oversight cost?

**Result:** On 12 small Python tasks, every generated solution passed its visible acceptance tests and 2 of the 12 still failed hidden tests. A separate reviewer model, with no shared context, flagged both of those solutions and one more that the hidden tests did not fault. One bounded revision fixed one of the two confirmed defects; the other revision returned byte-identical code. Review took 1.36× the coding time and 1.23× the coding tokens; review plus revision took 1.57× and 1.45×.

**Why it matters:** Passing deterministic tests did not mean the agent's code was correct. Independent review found the failures the tests missed, but the oversight had its own cost and its own failure modes: an unconfirmable flag and a revision that changed nothing. A verification layer in an agent system is itself a system to evaluate, not a feature to assume helpful. The accept-or-reject decision here stays with deterministic code.

**Status:** First run complete and frozen (run `20260927T192610Z-26ffea4d`). Platform under active development: later commits added a tool-loop coder and a Codex coder, exercised only in smoke runs.

## The first run

[`results/runs/20260927T192610Z-26ffea4d/`](results/runs/20260927T192610Z-26ffea4d/): Claude Haiku 4.5
writes each solution in one tool-less call. Claude Sonnet 5 reviews it in a separate call with no
shared context, and a flagged solution gets one revision. 12 small Python tasks, one episode each.
Each task has visible acceptance tests and a hidden held-out suite that no agent sees.

- **Deterministic tests:** 12/12 Haiku solutions passed the visible acceptance tests. **2 of those
  12 failed the hidden tests**, i.e. they had defects the acceptance tests missed.
- **Independent review:** Sonnet flagged 3 of the 12 test-passing solutions. The flags covered **both
  hidden-test-failing solutions (2/2 confirmed, 0 missed)** and 1 of the 10 hidden-test-passing
  solutions (unconfirmed). On post-hoc inspection (not a metric; see the
  [notes](results/runs/20260927T192610Z-26ffea4d/posthoc_notes.md)), both confirmed findings
  described the defect the failing hidden test checks.
- **Revision:** one bounded revision fixed 1 of the 2 confirmed defects. The other revision
  returned byte-identical code. Accepted solutions that failed hidden tests: 2/12 with tests only,
  0/9 with tests plus review, 1/12 with tests, review and revision.
- **Overhead:** reviewing cost more than coding. Review took 454 s against 333 s of coding (1.36×)
  and 114k against 93k CLI-reported tokens (input including cache reads, plus output; 1.23×). Review
  plus revision came to 1.57× the coding time and 1.45× the coding tokens.
- **Validity:** 0 provider, system or protocol failures and 0 control violations in 27 model calls.
  A post-hoc audit rebuilt all 27 prompts from the recorded inputs, matched each hash, and found no
  hidden-test file names, test names or failing-test identifiers in any of them (the check is
  name-based, not content-based).

These are counts from one run with one coder model and one reviewer model, not general rates. The
12 tasks were **intentionally designed** so that each written spec names edge cases (Unicode, input
validation, whitespace, mutation) that the visible tests do not exhaustively cover. Every number
above is in [`results/latest_metrics.json`](results/latest_metrics.json) and
[`results/latest_summary.md`](results/latest_summary.md).

## How one episode works

```
spec + starter + visible tests ─► coder (Haiku, no tools) ─► frozen commit in a private git repo
      ─► visible tests + hidden tests, each in a fresh directory (hidden results never reach an agent)
      ─► if visible pass: reviewer (Sonnet, separate call) sees spec + code + visible tests only
      ─► frozen flag rule: any finding with severity high/medium and confidence ≥ 0.6
      ─► if flagged: one revision from the findings ─► re-run both suites
```

Configurations are scored on the same coder output: **A** accepts if the visible tests pass; **B**
also requires that the review does not flag; **C** is B plus one revision. Every call is classified
as ok, a system failure (timeout, CLI or provider error, rate limit, control violation) or a
protocol failure (malformed output), with one counted retry. Every Claude call is also checked for
undeclared models, advisor use or tool use.

## Reproduce

```bash
python3 -m pip install -e .          # stdlib + pytest only
python3 -m pytest -q                 # 69 offline tests, no model calls
```

The analysis and audit commands write their output into the run directory they are given, and the
analysis code's cost fields have been renamed since the first run. To re-check the first run
without touching the committed records, work on a copy:

```bash
cp -r results/runs/20260927T192610Z-26ffea4d /tmp/arl-check
PYTHONPATH=src python3 -m agent_reliability analyze /tmp/arl-check --no-latest
PYTHONPATH=src python3 -m agent_reliability.analysis.protocol_checks /tmp/arl-check
```

Every count and ratio in the regenerated `metrics.json` matches the committed file; only the cost
key names differ. The full CLI event streams (`raw/`) are not committed because they contain
session IDs and local paths, so a fresh clone can rerun the prompt, leakage and freeze checks but
not the per-call raw-trace checks. Those passed at run time and are recorded in
`protocol_audit.json`. A new experiment needs a logged-in Claude Code CLI and writes a new run
directory:

```bash
PYTHONPATH=src python3 -m agent_reliability run --config configs/cross_review_v1.json
```

## What these results do not show

- **That independent review improves coding agents in general.** One coder model, one reviewer
  model (both Claude, different sizes), 12 tasks, and one repetition.
- **Rates with useful precision.** The task-clustered bootstrap 95% intervals are wide: [0, 0.42]
  for the hidden-defect rate among test-passing solutions, and [0, 0.50] for the flag rate.
- **That the hidden tests are complete ground truth.** The experimenter wrote them; nobody labelled
  them independently. Visible suites are three happy-path tests per task; hidden suites have 3 to 13.
  The one "unconfirmed" flag (`roman_to_int('III\n')` raises `KeyError`, not the specified
  `ValueError`) reproduces on inspection as a real spec violation that the hidden tests do not
  cover. See [post-hoc notes](results/runs/20260927T192610Z-26ffea4d/posthoc_notes.md). The metric
  still counts it as unconfirmed, because that rule was fixed before the run.
- **How often acceptance tests miss defects in real projects.** The tasks were built to leave that
  gap open.
- **Money.** Costs are CLI-reported tokens and list-price metadata ($0.28 for coding, $0.57 for
  review plus revision), not invoices.
- **Agentic coding.** The first run's coder made one tool-less call per task. The model-identity
  control accepts CLI aliases, so the same alias resolving to a different model version across runs
  would not be caught.

Two later smoke runs are committed under `results/runs/` (a one-episode tool-loop run and a
six-episode run with a Codex coder). They exercise new code paths, are not audited to the same
standard (the Codex run was made from a dirty tree and has no protocol audit), and do not change
the numbers above. In the Codex run all 3 flags were unconfirmed, a reminder that unconfirmed flags
can be frequent.

## Motivation and lineage

This project continues three earlier repositories of mine. It reuses and rewrites ideas from them;
it does not merge them. See [docs/provenance.md](docs/provenance.md) for commits and a file-level map.

- **[agent-workflow-orchestrator](https://github.com/retinapeg/agent-workflow-orchestrator)** supplied the coding workload. Its `VALIDATION.md` records one live
  run in which *"the Codex review found a real Unicode lowercasing edge case in Claude's initial
  implementation; Claude accepted and fixed it during revision."* That single documented observation
  prompted this experiment; it is not treated as evidence of a rate.
- **[agentic-physics-bench](https://github.com/retinapeg/agentic-physics-bench)** supplied the validity discipline. The lesson was that aggregate scores
  are not evidence if the trace is contaminated: there, a server-side advisor had silently added a
  second model to "tool-less" calls. Here every call is checked for that.
- **[institutional-workbench](https://github.com/retinapeg/institutional-workbench)** supplied the failure taxonomy that separates model failures from
  system and protocol failures.

## Documentation

- [docs/architecture.md](docs/architecture.md): diagram, control flow, where each check happens,
  and the shortcuts taken
- [docs/methodology.md](docs/methodology.md): tasks, configurations, outcome definitions and
  statistical limitations
- [docs/provenance.md](docs/provenance.md): source commits, what was adapted, what was left out
- [results/latest_summary.md](results/latest_summary.md): generated answers to the ten result questions

## Layout

```
configs/                              frozen experiment configs (models, flag rule, retries):
                                      cross_review_v1 (first run), _tool_loop_v1, _v2_codex
experiments/coding_cross_review/tasks 12 tasks: spec, starter, visible tests, hidden tests, reference
src/agent_reliability/
  agents/        Claude/Codex CLI agents (tool-less and tool-loop) + scripted test agent
  environments/  tasks, private git workspace, solution extraction
  verifiers/     pytest in a fresh directory, JUnit parsing
  review/        review prompt, strict JSON parsing, frozen flag rule
  reliability/   failure taxonomy and per-call control checks
  runners/       one episode: code → verify → review → revise
  traces/        write-once run directories, append-only JSONL
  analysis/      metrics, summary, post-hoc protocol audit
  pricing.py     list-price cost estimates from token counts
results/runs/<run_id>/                run.json, attempts.jsonl, episodes.jsonl, metrics, summary,
                                      and (first run) protocol audit and post-hoc notes
```

MIT licensed.
