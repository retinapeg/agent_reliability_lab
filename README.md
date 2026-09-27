# Agent Reliability Lab

A reproducible experimental platform for testing whether agent oversight and verification catch
failures that conventional acceptance tests miss.

## Current experiment

Does independent coding-agent review identify meaningful defects missed by deterministic tests,
and what additional latency and cost does that oversight introduce?

First run, [`20260927T192610Z-26ffea4d`](results/runs/20260927T192610Z-26ffea4d/): Claude Haiku 4.5
writes each solution in one tool-less call. Claude Sonnet 5 reviews it in a separate call with no
shared context, and a flagged solution gets one revision. The run used 12 small Python tasks, one
episode each. Each task has visible acceptance tests and a hidden held-out suite that no agent sees.

## Key results

On this 12-task benchmark:

- **Deterministic tests:** 12/12 Haiku solutions passed the visible acceptance tests. **2 of those
  12 failed the hidden tests**, i.e. they had defects the acceptance tests missed.
- **Independent review:** Sonnet flagged 3 of the 12 test-passing solutions. The flags covered **both
  hidden-test-failing solutions (2/2 confirmed, 0 missed)** and 1 of the 10 hidden-test-passing
  solutions (unconfirmed). In both confirmed cases the finding described the defect the hidden
  test caught.
- **Revision:** one bounded revision fixed 1 of the 2 confirmed defects. The other revision
  returned byte-identical code. Accepted solutions that failed hidden tests: 2/12 with tests only,
  0/9 with tests plus review, 1/12 with tests, review and revision.
- **Overhead:** reviewing cost more than coding. Review took 454 s against 333 s of coding (1.36×)
  and 114k against 93k CLI-reported tokens. Review plus revision came to 1.57× the coding time and
  1.45× the coding tokens.
- **Validity:** there were 0 provider, system or protocol failures and 0 control violations in 27
  model calls. A post-hoc audit rebuilt all 27 prompts from the recorded inputs, matched each hash,
  and found no hidden-test content in any of them.

These are counts from one run with one coder model and one reviewer model, not general rates. The
12 tasks were **intentionally designed** so that each written spec names edge cases (Unicode, input
validation, whitespace, mutation) that the visible tests do not exhaustively cover. Every number
above is in [`results/latest_metrics.json`](results/latest_metrics.json) and
[`results/latest_summary.md`](results/latest_summary.md).

## Why this matters

Passing tests do not necessarily imply a correct implementation. An agent review may catch
semantic or edge-case failures that a deterministic test suite misses. But oversight also adds
cost and latency, and it has its own error modes: flags that cannot be confirmed, and revisions
that do not fix the problem. This project measures both the potential benefit and the overhead
and failure modes of that oversight. The accept or reject decision stays with deterministic code.

## Reproduce

```bash
python3 -m pip install -e .          # stdlib + pytest only
python3 -m pytest -q                 # 57 offline tests, no model calls
# Regenerate metrics and the summary from committed episode records (no model calls):
PYTHONPATH=src python3 -m agent_reliability analyze results/runs/20260927T192610Z-26ffea4d
# Re-check prompt reconstruction, hidden-test leakage and file freeze (no model calls):
PYTHONPATH=src python3 -m agent_reliability.analysis.protocol_checks results/runs/20260927T192610Z-26ffea4d
# Run a new experiment (needs a logged-in Claude Code CLI; writes a new run directory):
PYTHONPATH=src python3 -m agent_reliability run --config configs/cross_review_v1.json
```

The full CLI event streams (`raw/`) are not committed because they contain session IDs and local
paths. A fresh clone can therefore rerun the prompt, leakage and freeze checks, but not the per-call
raw-trace checks. Those passed at run time and are recorded in `protocol_audit.json`.

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

## What these results do not show

- **That independent review improves coding agents in general.** One coder model, one reviewer
  model (both Claude, different sizes), 12 tasks, and one repetition.
- **Rates with useful precision.** The task-clustered bootstrap 95% intervals are wide: [0, 0.42]
  for the hidden-defect rate among test-passing solutions, and [0, 0.50] for the flag rate.
- **That the hidden tests are complete ground truth.** The experimenter wrote them; nobody labelled
  them independently. The one "unconfirmed" flag (`roman_to_int('III\n')` raises `KeyError`, not
  the specified `ValueError`) reproduces on inspection as a real spec violation that the hidden
  tests do not cover. See [post-hoc notes](results/runs/20260927T192610Z-26ffea4d/posthoc_notes.md).
  The metric still counts it as unconfirmed, because that rule was fixed before the run.
- **How often acceptance tests miss defects in real projects.** The tasks were built to leave that
  gap open.
- **Money.** Costs are CLI-reported tokens and list-price metadata ($0.28 for coding, $0.57 for
  review plus revision), not invoices.

## Motivation and lineage

This project continues three earlier repositories of mine. It reuses and rewrites ideas from them;
it does not merge them. See [docs/provenance.md](docs/provenance.md) for commits and a file-level map.

- **agent-workflow-orchestrator** supplied the coding workload. Its `VALIDATION.md` records one live
  run in which *"the Codex review found a real Unicode lowercasing edge case in Claude's initial
  implementation; Claude accepted and fixed it during revision."* That single documented observation
  prompted this experiment; it is not treated as evidence of a rate.
- **agentic-physics-bench** supplied the validity discipline. The lesson was that aggregate scores
  are not evidence if the trace is contaminated: there, a server-side advisor had silently added a
  second model to "tool-less" calls. Here every call is checked for that.
- **institutional-workbench** supplied the failure taxonomy that separates model failures from
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
configs/cross_review_v1.json          frozen experiment config (models, flag rule, retries)
experiments/coding_cross_review/tasks 12 tasks: spec, starter, visible tests, hidden tests, reference
src/agent_reliability/
  agents/        tool-less Claude/Codex CLI agents + scripted test agent
  environments/  tasks, private git workspace, solution extraction
  verifiers/     pytest in a fresh directory, JUnit parsing
  review/        review prompt, strict JSON parsing, frozen flag rule
  reliability/   failure taxonomy and per-call control checks
  runners/       one episode: code → verify → review → revise
  traces/        write-once run directories, append-only JSONL
  analysis/      metrics, summary, post-hoc protocol audit
results/runs/<run_id>/                run.json, attempts.jsonl, episodes.jsonl, metrics, audit
```

MIT licensed.
