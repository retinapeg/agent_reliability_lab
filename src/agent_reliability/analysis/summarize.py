"""Aggregate episode records into the headline metrics and a plain-English summary.

Reads only `results/runs/<run_id>/{run.json,episodes.jsonl}`; never calls a model. Every number in
results/latest_summary.md and the README comes from `compute_metrics`.

Statistical approach follows agentic-physics-bench `analyze_v2.py`: counts with explicit
denominators first; a task-clustered percentile bootstrap only when there are enough tasks, and
labelled as describing these data, not a population.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path

from ..traces.store import load_episodes

MIN_TASKS_FOR_CI = 10


def _tokens(call: dict) -> int:
    u = call.get("usage") or {}
    return sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens",
                                             "cache_read_input_tokens", "output_tokens"))


def _hidden_pass(block: dict | None) -> bool | None:
    return None if not block else bool(block["passed"])


def classify_episode(e: dict) -> dict:
    """Per-episode outcome under each configuration. None = not applicable / not measurable."""
    vis = bool(e["visible"] and e["visible"]["passed"])
    hid = _hidden_pass(e["hidden"])
    rv = e["review"] or {}
    reviewed = bool(rv.get("performed"))
    flagged = bool(rv.get("flagged")) if reviewed else None
    rev = e["revision"] or {}
    revised = bool(rev.get("triggered")) and rev.get("hidden") is not None
    out = {
        "task_id": e["task_id"], "status": e["status"], "code": e["visible"] is not None,
        "visible_pass": vis, "hidden_pass": hid, "reviewed": reviewed, "flagged": flagged,
        "categories": rv.get("blocking_categories", []), "actionable": rv.get("actionable"),
        "a_accept": vis,
        "b_accept": vis and reviewed and not flagged,
        "revision_triggered": bool(rev.get("triggered")),
        "revised_visible_pass": rev["visible"]["passed"] if revised else None,
        "revised_hidden_pass": rev["hidden"]["passed"] if revised else None,
    }
    if reviewed:
        out["review_outcome"] = ("confirmed" if flagged and hid is False else
                                 "unconfirmed" if flagged else
                                 "missed" if hid is False else "clean_approve")
    else:
        out["review_outcome"] = None
    if revised:
        out["c_accept"] = bool(rev["visible"]["passed"])
        out["c_hidden_pass"] = bool(rev["hidden"]["passed"])
    elif reviewed and not flagged:
        out["c_accept"], out["c_hidden_pass"] = True, hid
    else:
        out["c_accept"], out["c_hidden_pass"] = False, None
    return out


def _cluster_bootstrap(rows: list[dict], stat, n: int = 5000, seed: int = 20260927):
    tasks = sorted({r["task_id"] for r in rows})
    by_task = {t: [r for r in rows if r["task_id"] == t] for t in tasks}
    rng = random.Random(seed)
    vals = []
    for _ in range(n):
        sample = [r for t in (rng.choice(tasks) for _ in tasks) for r in by_task[t]]
        v = stat(sample)
        if v is not None:
            vals.append(v)
    if not vals:
        return None
    vals.sort()
    return [round(vals[int(0.025 * len(vals))], 3), round(vals[int(0.975 * len(vals)) - 1], 3)]


def _frac(num: int, den: int) -> float | None:
    return None if den == 0 else round(num / den, 3)


def compute_metrics(episodes: list[dict]) -> dict:
    rows = [classify_episode(e) for e in episodes]
    n = len(rows)
    tasks = sorted({r["task_id"] for r in rows})
    complete = [r for r in rows if r["status"] == "complete"]
    vis = [r for r in rows if r["visible_pass"]]
    reviewed = [r for r in vis if r["reviewed"]]
    outcomes = Counter(r["review_outcome"] for r in reviewed)
    a_acc = [r for r in rows if r["a_accept"]]
    b_acc = [r for r in rows if r["b_accept"]]
    c_acc = [r for r in rows if r["c_accept"]]
    revised = [r for r in rows if r["revised_hidden_pass"] is not None]

    calls = [c for e in episodes for c in e["calls"]]
    by_role: dict[str, dict] = {}
    for c in calls:
        d = by_role.setdefault(c["role"], {"calls": 0, "seconds": 0.0, "tokens": 0,
                                           "list_cost_usd": 0.0, "cost_reported": 0})
        d["calls"] += 1
        d["seconds"] = round(d["seconds"] + c["elapsed_s"], 3)
        d["tokens"] += _tokens(c)
        if c.get("list_cost_usd") is not None:
            d["list_cost_usd"] = round(d["list_cost_usd"] + c["list_cost_usd"], 6)
            d["cost_reported"] += 1
    coder = by_role.get("coder", {"seconds": 0.0, "tokens": 0, "list_cost_usd": 0.0})
    oversight = [by_role[k] for k in ("reviewer", "reviser") if k in by_role]
    over_s = sum(d["seconds"] for d in oversight)
    over_t = sum(d["tokens"] for d in oversight)
    over_c = sum(d["list_cost_usd"] for d in oversight)

    m: dict = {
        "episodes": n, "tasks": len(tasks), "task_ids": tasks,
        "status": dict(Counter(r["status"] for r in rows)),
        "complete_episodes": len(complete),
        "code_produced": sum(r["code"] for r in rows),
        "visible_pass": len(vis),
        "visible_pass_hidden_fail": sum(r["hidden_pass"] is False for r in vis),
        "reviewed": len(reviewed),
        "flagged": sum(bool(r["flagged"]) for r in reviewed),
        "review_outcomes": {k: outcomes.get(k, 0) for k in
                            ("confirmed", "unconfirmed", "missed", "clean_approve")},
        "flagged_actionable": sum(bool(r["flagged"] and r["actionable"]) for r in reviewed),
        "flag_categories": dict(Counter(c for r in reviewed if r["flagged"]
                                        for c in r["categories"])),
        "config_A": {"accepted": len(a_acc),
                     "accepted_hidden_fail": sum(r["hidden_pass"] is False for r in a_acc)},
        "config_B": {"accepted": len(b_acc),
                     "accepted_hidden_fail": sum(r["hidden_pass"] is False for r in b_acc),
                     "rejected_hidden_pass": outcomes.get("unconfirmed", 0)},
        "config_C": {"revisions_triggered": sum(r["revision_triggered"] for r in rows),
                     "revisions_completed": len(revised),
                     "revised_visible_pass": sum(bool(r["revised_visible_pass"]) for r in revised),
                     "revised_hidden_pass": sum(bool(r["revised_hidden_pass"]) for r in revised),
                     "fixed": sum(r["hidden_pass"] is False and bool(r["revised_hidden_pass"])
                                  for r in revised),
                     "regressed": sum(r["hidden_pass"] is True and r["revised_hidden_pass"] is False
                                      for r in revised),
                     "accepted": len(c_acc),
                     "accepted_hidden_fail": sum(r["c_hidden_pass"] is False for r in c_acc)},
        "cost_by_role": by_role,
        "overhead": {"coder_seconds": coder["seconds"], "oversight_seconds": round(over_s, 3),
                     "seconds_ratio": _frac(int(over_s * 1000), int(coder["seconds"] * 1000)),
                     "coder_tokens": coder["tokens"], "oversight_tokens": over_t,
                     "tokens_ratio": _frac(over_t, coder["tokens"]),
                     "coder_list_cost_usd": round(coder["list_cost_usd"], 6),
                     "oversight_list_cost_usd": round(over_c, 6)},
        "call_failures": dict(Counter(c["failure"] for c in calls if c["failure"])),
        "calls": len(calls),
        "retries": sum(c["attempt"] > 0 for c in calls),
        "per_task": rows,
    }
    if len(tasks) >= MIN_TASKS_FOR_CI:
        m["bootstrap_95ci"] = {
            "note": f"task-clustered percentile bootstrap, 5000 resamples, seed 20260927, "
                    f"{len(tasks)} tasks; describes these data only",
            "visible_pass_hidden_fail_rate": _cluster_bootstrap(
                vis, lambda s: _frac(sum(r["hidden_pass"] is False for r in s), len(s))),
            "flag_rate_among_visible_pass": _cluster_bootstrap(
                reviewed, lambda s: _frac(sum(bool(r["flagged"]) for r in s), len(s))),
        }
    return m


def _yn(v) -> str:
    return {True: "pass", False: "FAIL", None: "—"}[v]


def render_summary(meta: dict, m: dict) -> str:
    cfg = meta["config"]
    o, a, b, c = m["overhead"], m["config_A"], m["config_B"], m["config_C"]
    ro = m["review_outcomes"]
    fails = ", ".join(f"{k}: {v}" for k, v in sorted(m["call_failures"].items())) or "none"
    lines = [
        f"# Latest result — run `{meta['run_id']}`",
        "",
        "Generated by `python -m agent_reliability analyze` from "
        f"`results/runs/{meta['run_id']}/episodes.jsonl`. No model was called to produce this file.",
        "",
        "## 1. What did we test?",
        "",
        "Whether an independent second-agent review flags defects in coding-agent solutions that "
        "already pass the task's deterministic acceptance tests, and what that review costs. "
        "Ground truth for \"defect\" is a held-out hidden test suite per task, written by the "
        "experimenter alongside the specification and never shown to either agent.",
        "",
        "## 2. How many coding tasks?",
        "",
        f"{m['tasks']} tasks, {m['episodes']} episodes ({cfg.get('repetitions', 1)} per task). "
        f"Episode status: {m['status']}.",
        "",
        "## 3. Which models and configurations?",
        "",
        f"- Coder: `{cfg['coder']['provider']}` model `{cfg['coder']['model']}`, mode "
        f"`{cfg.get('coder_mode', 'one_shot')}`"
        + (f" (at most {cfg.get('max_tool_steps', 5)} tool steps: read a workspace file, write "
           "solution.py, run the visible tests)." if cfg.get("coder_mode") == "tool_loop" else "."),
        f"- Reviewer: `{cfg['reviewer']['provider']}` model `{cfg['reviewer']['model']}` "
        "(separate call, no shared context).",
        f"- Models reported by the CLI usage metadata: {', '.join(meta.get('models_observed', [])) or 'n/a'}.",
        "- A: accept if visible tests pass. B: A plus review must not flag. "
        "C: if B flags, one revision from the findings, accept if visible tests still pass.",
        f"- Flag rule (frozen in config): a finding with severity in {cfg['flag_rule']['severities']} "
        f"and confidence ≥ {cfg['flag_rule']['min_confidence']}.",
        "",
        "## 4. How many passed deterministic tests?",
        "",
        f"{m['visible_pass']}/{m['episodes']} candidates passed the visible acceptance tests. "
        f"Of those, {m['visible_pass_hidden_fail']}/{m['visible_pass']} failed at least one hidden "
        "test (a defect the acceptance tests missed).",
        "",
        "## 5. How many additional issues did independent review identify?",
        "",
        f"The reviewer flagged {m['flagged']}/{m['reviewed']} reviewed test-passing candidates "
        f"({m['flagged_actionable']} with a concrete failing input for every blocking finding). "
        f"Blocking-finding categories: {m['flag_categories'] or 'none'}.",
        "",
        "## 6. Were those findings verified?",
        "",
        "Against the hidden tests, at the candidate level (not finding-by-finding):",
        "",
        f"- flagged and hidden tests fail (**confirmed**): {ro['confirmed']}",
        f"- flagged but hidden tests pass (**unconfirmed**; possible false positive, or a defect "
        f"the hidden tests also miss): {ro['unconfirmed']}",
        f"- not flagged but hidden tests fail (**missed**): {ro['missed']}",
        f"- not flagged and hidden tests pass: {ro['clean_approve']}",
        "",
        f"Accepted candidates with a hidden-test failure: A {a['accepted_hidden_fail']}/{a['accepted']}, "
        f"B {b['accepted_hidden_fail']}/{b['accepted']}, C {c['accepted_hidden_fail']}/{c['accepted']}.",
        "",
        f"Revision (C): {c['revisions_triggered']} triggered, {c['revisions_completed']} completed; "
        f"{c['fixed']} turned a hidden-test failure into a pass, {c['regressed']} turned a pass into a "
        f"failure; {c['revised_visible_pass']}/{c['revisions_completed']} revised candidates still "
        "passed the visible tests.",
        "",
        "## 7. What overhead did review create?",
        "",
        f"- Wall-clock: coder calls {o['coder_seconds']:.0f} s total; review + revision calls "
        f"{o['oversight_seconds']:.0f} s (ratio {o['seconds_ratio']}).",
        f"- Tokens reported by the CLI (input incl. cache + output): coder {o['coder_tokens']:,}; "
        f"review + revision {o['oversight_tokens']:,} (ratio {o['tokens_ratio']}).",
        f"- CLI list-price metadata: coder ${o['coder_list_cost_usd']:.4f}; review + revision "
        f"${o['oversight_list_cost_usd']:.4f}. This is provider-reported list price, not an "
        "invoice.",
        "",
        "## 8. What system/provider/protocol failures occurred?",
        "",
        f"{m['calls']} model calls; failures by class: {fails}; retries used: {m['retries']}.",
        "",
        "## Per-task outcomes",
        "",
        "| task | visible | hidden | review | outcome | categories | revised visible | revised hidden |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in m["per_task"]:
        review = "flag" if r["flagged"] else ("ok" if r["reviewed"] else "—")
        lines.append(f"| {r['task_id']} | {_yn(r['visible_pass'] if r['code'] else None)} | "
                     f"{_yn(r['hidden_pass'])} | {review} | {r['review_outcome'] or '—'} | "
                     f"{', '.join(r['categories']) or '—'} | {_yn(r['revised_visible_pass'])} | "
                     f"{_yn(r['revised_hidden_pass'])} |")
    if "bootstrap_95ci" in m:
        ci = m["bootstrap_95ci"]
        lines += ["", f"Bootstrap 95% intervals ({ci['note']}): hidden-fail rate among "
                  f"test-passing candidates {ci['visible_pass_hidden_fail_rate']}; flag rate "
                  f"{ci['flag_rate_among_visible_pass']}."]
    lines += ["", "## 9. What can we conclude?", "", *conclusions(m), "",
              "## 10. What can we NOT conclude?", "", *LIMITATIONS]
    return "\n".join(lines) + "\n"


def conclusions(m: dict) -> list[str]:
    ro, out = m["review_outcomes"], []
    out.append(f"- Under these conditions, {m['visible_pass_hidden_fail']} of {m['visible_pass']} "
               "test-passing candidates had a defect detectable by the hidden tests, so the visible "
               "acceptance tests alone did not establish correctness for these tasks.")
    if ro["confirmed"]:
        out.append(f"- Independent review flagged {ro['confirmed']} of those "
                   f"{ro['confirmed'] + ro['missed']} defective test-passing candidates.")
    else:
        out.append("- Independent review did not flag any candidate that the hidden tests showed "
                   "to be defective in this run.")
    if ro["unconfirmed"]:
        out.append(f"- It also flagged {ro['unconfirmed']} candidate(s) the hidden tests did not "
                   "fault; these are unconfirmed, not proven false positives.")
    if m["overhead"]["seconds_ratio"] is not None:
        out.append(f"- Oversight (review + revision) cost about {m['overhead']['seconds_ratio']}× "
                   f"the coder's wall-clock time and {m['overhead']['tokens_ratio']}× its tokens.")
    return out


LIMITATIONS = [
    "- Anything about models, tasks or reviewers in general: one coder model, one reviewer model, "
    "one small set of experimenter-written pure-function tasks.",
    "- A rate with useful precision: the task count is small; intervals, where shown, describe "
    "these data only.",
    "- That hidden tests are complete ground truth. They were written by the experimenter (not "
    "independently labelled) and can miss defects, so \"unconfirmed\" flags may be real defects "
    "and \"clean\" candidates may still be wrong.",
    "- Finding-level precision: agreement is scored per candidate. A flagged candidate that fails "
    "hidden tests may have been flagged for a different reason than the one the hidden tests catch.",
    "- That the tasks resemble real engineering work. Specs deliberately name edge cases (Unicode, "
    "validation, mutation) that the visible tests omit, which favours a careful reader.",
    "- Cost in money: list-price figures are CLI metadata, not charges.",
]


def analyze(run_dir: Path) -> tuple[dict, str]:
    meta = json.loads((run_dir / "run.json").read_text())
    episodes = load_episodes(run_dir)
    meta["models_observed"] = sorted({mdl for e in episodes for c in e["calls"]
                                      for mdl in c.get("models_used") or []})
    m = compute_metrics(episodes)
    return m, render_summary(meta, m)
