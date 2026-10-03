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

from ..pricing import LABEL, PriceTable, default_pricing_path, load_price_table, price_call
from ..traces.store import load_episodes

MIN_TASKS_FOR_CI = 10


def _tokens(call: dict) -> int:
    u = call.get("usage") or {}
    return sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens",
                                             "cache_read_input_tokens", "output_tokens"))


def pricing_call(call: dict) -> dict:
    """A recorded call as raw token counts in the shape `pricing.price_call` expects."""
    u = call.get("usage") or {}
    models = call.get("models_used") or []
    out = {"call": call.get("role"), "model": models[0] if len(models) == 1 else call.get("model"),
           "input": u.get("input_tokens"), "output": u.get("output_tokens")}
    if call.get("provider") == "codex_cli":
        out.update(cache_read=u.get("cached_input_tokens"),
                   cache_write=u.get("cache_write_input_tokens"),
                   reasoning=u.get("reasoning_output_tokens"),
                   input_includes_cache_read=True)  # Codex input_tokens counts cached tokens
    else:
        split = u.get("cache_creation") if isinstance(u.get("cache_creation"), dict) else {}
        out.update(cache_read=u.get("cache_read_input_tokens"),
                   cache_write=u.get("cache_creation_input_tokens"),
                   reasoning=None, not_applicable=["reasoning"],  # thinking is billed as output
                   input_includes_cache_read=False)
        if split:
            out.update(cache_write_5m=split.get("ephemeral_5m_input_tokens"),
                       cache_write_1h=split.get("ephemeral_1h_input_tokens"))
    return out


def call_cost(call: dict, table: PriceTable) -> dict:
    """cost_usd and cost_source for one call; dollars are derived here, never stored in a trace.

    cli_reported if the CLI gave a cost, else api_estimate from the tokens and the price table,
    else unpriced (cost_usd None, never 0). `api_estimate_usd` is always computed when possible
    so reported and estimated costs can be compared for the same call.
    """
    priced = price_call(pricing_call(call), table)
    estimate = None if priced.cost is None else round(float(priced.cost), 6)
    reported = call.get("list_cost_usd")
    if reported is not None:
        cost, source = round(float(reported), 6), "cli_reported"
    elif estimate is not None:
        cost, source = estimate, "api_estimate"
    else:
        cost, source = None, "unpriced"
    return {"cost_usd": cost, "cost_source": source, "api_estimate_usd": estimate,
            "unpriced_reason": priced.missing if cost is None else None,
            "no_cache_split": any("no 5m/1h" in n for n in priced.notes)}


def _cost_total(roles: list[dict]) -> dict:
    """Sum over roles: cost of the priced calls plus coverage; None (not 0) when none priced."""
    priced = sum(d["calls_priced"] for d in roles)
    return {"cost_usd": round(sum(d["cost_usd"] or 0.0 for d in roles), 6) if priced else None,
            "calls_priced": priced, "calls": sum(d["calls"] for d in roles)}


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


def compute_metrics(episodes: list[dict], table: PriceTable | None = None) -> dict:
    table = table if table is not None else load_price_table(default_pricing_path())
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
    call_costs: list[dict] = []
    check = {"calls": 0, "cli_reported_usd": 0.0, "api_estimate_usd": 0.0, "no_cache_split": 0}
    for e in episodes:
        for c in e["calls"]:
            d = by_role.setdefault(c["role"], {
                "calls": 0, "seconds": 0.0, "tokens": 0, "cost_usd": None, "calls_priced": 0,
                "cost_sources": {"cli_reported": 0, "api_estimate": 0, "unpriced": 0}})
            d["calls"] += 1
            d["seconds"] = round(d["seconds"] + c["elapsed_s"], 3)
            d["tokens"] += _tokens(c)
            cost = call_cost(c, table)
            d["cost_sources"][cost["cost_source"]] += 1
            if cost["cost_usd"] is not None:  # an unpriced call adds nothing and is never 0
                d["cost_usd"] = round((d["cost_usd"] or 0.0) + cost["cost_usd"], 6)
                d["calls_priced"] += 1
            call_costs.append({"episode_id": e["episode_id"], "role": c["role"],
                               "model": c.get("model"), **cost})
            if cost["cost_source"] == "cli_reported" and cost["api_estimate_usd"] is not None:
                check["calls"] += 1
                check["cli_reported_usd"] = round(check["cli_reported_usd"] + cost["cost_usd"], 6)
                check["api_estimate_usd"] = round(
                    check["api_estimate_usd"] + cost["api_estimate_usd"], 6)
                check["no_cache_split"] += cost["no_cache_split"]
    check["gap_pct"] = (round(100 * (check["api_estimate_usd"] / check["cli_reported_usd"] - 1), 1)
                        if check["cli_reported_usd"] else None)
    coder = by_role.get("coder", {"seconds": 0.0, "tokens": 0, "calls": 0, "calls_priced": 0,
                                  "cost_usd": None})
    oversight = [by_role[k] for k in ("reviewer", "reviser") if k in by_role]
    over_s = sum(d["seconds"] for d in oversight)
    over_t = sum(d["tokens"] for d in oversight)

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
                     "coder_cost": _cost_total([coder]),
                     "oversight_cost": _cost_total(oversight)},
        "cost_label": LABEL,
        "pricing": {"version": table.version, "sha256": table.sha256},
        "call_costs": call_costs,
        "cost_cross_check": check,
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


def _cost(c: dict) -> str:
    """"$X (k/n calls priced)"; "not reported" when no call is priced. Never $0.0000 for unknown."""
    if not c["calls_priced"]:
        return f"not reported (0/{c['calls']} calls priced)"
    return f"${c['cost_usd']:.4f} ({c['calls_priced']}/{c['calls']} calls priced)"


def _cross_check(x: dict) -> str:
    if not x["calls"]:
        return ("- Claude cross-check: no call has both a CLI-reported cost and a token-based "
                "estimate.")
    line = (f"- Claude cross-check ({x['calls']} calls with both figures): CLI-reported "
            f"${x['cli_reported_usd']:.4f} vs API estimate ${x['api_estimate_usd']:.4f} "
            f"(estimate {x['gap_pct']:+.1f}%). A big gap means a wrong price.")
    if x["no_cache_split"]:
        line += (f" {x['no_cache_split']} of these calls recorded no 5m/1h cache-write split and "
                 "were estimated at the 5m rate, which understates 1h cache writes.")
    return line


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
        f"- Cost, {m['cost_label']}, price table version {m['pricing']['version']}: coder "
        f"{_cost(o['coder_cost'])}; review + revision {_cost(o['oversight_cost'])}. A call's "
        "cost is the CLI-reported figure when there is one, else an estimate from its tokens; "
        "an unpriced call is left out, never counted as $0.",
        _cross_check(m["cost_cross_check"]),
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
    "- Cost in money: the figures are API-equivalent list prices, not charges.",
]


def analyze(run_dir: Path) -> tuple[dict, str]:
    meta = json.loads((run_dir / "run.json").read_text())
    episodes = load_episodes(run_dir)
    meta["models_observed"] = sorted({mdl for e in episodes for c in e["calls"]
                                      for mdl in c.get("models_used") or []})
    m = compute_metrics(episodes)
    return m, render_summary(meta, m)
