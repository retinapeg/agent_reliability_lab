"""Post-hoc protocol audit of one run directory. Reads files only; never calls a model.

Checks, per episode and per call:
  1. prompt reconstruction: every coder/reviewer/reviser prompt is rebuilt from the recorded inputs
     with the same prompt builders; its SHA-256 must equal the recorded `prompt_sha256`. A match
     proves exactly which inputs the agent saw.
  2. hidden-test leakage: no rebuilt prompt contains the hidden file name or any hidden-only test
     function name, and no hidden-test result appears in a prompt.
  3. controls: no control violation, exactly the declared model in `modelUsage`, no tool, server-tool
     or advisor block anywhere in the raw event stream, empty tool and MCP lists at init.
  4. freeze: task files and config hash match what `run.json` recorded at the start of the run.
  5. run directory: attempts written for every episode.

Usage: python -m agent_reliability.analysis.protocol_checks results/runs/<run_id>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from ..environments.coding.environment import HIDDEN, VISIBLE, Task
from ..review.reviewer import FlagRule, Finding, build_review_prompt, build_revision_prompt
from ..runners.cross_review import build_coder_prompt
from ..traces.store import load_episodes, sha256_text


def _hidden_only_names(task: Task) -> list[str]:
    hidden = set(re.findall(r"def (test_\w+)", (task.root / HIDDEN).read_text()))
    visible = set(re.findall(r"def (test_\w+)", (task.root / VISIBLE).read_text()))
    return sorted(hidden - visible)


def _walk(obj, path=""):
    """Yield (path, key, value) for every dict entry in a nested JSON value."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield path, k, v
            yield from _walk(v, f"{path}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")


def raw_trace_problems(events: list[dict]) -> list[str]:
    """Structural checks on one Claude CLI event stream.

    Structural, not substring: the result event always carries a usage counter named
    `server_tool_use` ({"web_search_requests": 0, ...}); a non-zero counter is a violation, the key
    itself is not.
    """
    out = []
    for i, ev in enumerate(events):
        if ev.get("type") == "system" and ev.get("subtype") == "init":
            if ev.get("tools") or ev.get("mcp_servers"):
                out.append("tools/MCP present at init")
        for path, key, value in _walk(ev, f"events[{i}]"):
            if key == "type" and value in ("tool_use", "server_tool_use", "advisor_tool_result"):
                out.append(f"{value} block at {path}")
            if "advisor" in key.lower() or (key == "type" and "advisor" in str(value).lower()):
                out.append(f"advisor marker at {path}/{key}")
            if key == "server_tool_use" and isinstance(value, dict) and any(value.values()):
                out.append(f"non-zero server tool usage at {path}: {value}")
        if ev.get("type") == "result" and len(ev.get("modelUsage") or {}) != 1:
            out.append(f"modelUsage has {sorted((ev.get('modelUsage') or {}))}")
    return out


def audit(run_dir: Path, root: Path) -> dict:
    meta = json.loads((run_dir / "run.json").read_text())
    cfg = meta["config"]
    rule = FlagRule(tuple(cfg["flag_rule"]["severities"]), cfg["flag_rule"]["min_confidence"])
    expected_model = {"coder": cfg["coder"]["model"], "reviser": cfg["coder"]["model"],
                      "reviewer": cfg["reviewer"]["model"]}
    episodes = load_episodes(run_dir)
    problems: list[str] = []
    n_prompts = n_calls = raw_missing = 0

    for e in episodes:
        task = Task(e["task_id"], root / cfg["tasks_dir"] / e["task_id"])
        forbidden = [HIDDEN, "test_hidden"] + _hidden_only_names(task)
        forbidden += (e.get("hidden") or {}).get("failed_tests") or []
        prompts: dict[str, str] = {"coder": build_coder_prompt(task)}
        code = (e["coder"] or {}).get("code")
        if code is not None and e["visible"] and e["visible"]["passed"]:
            prompts["reviewer"] = build_review_prompt(task.spec, code, task.visible_tests,
                                                      e["visible"])
            findings = [Finding(**f) for f in (e["review"] or {}).get("findings") or []]
            blocking = [f for f in findings
                        if f.severity in rule.severities and f.confidence >= rule.min_confidence]
            prompts["reviser"] = build_revision_prompt(task.spec, code, blocking)
        for call in e["calls"]:
            n_calls += 1
            where = f"{e['episode_id']}/{call['role']}#{call['attempt']}"
            prompt = prompts.get(call["role"])
            if prompt is None or sha256_text(prompt) != call["prompt_sha256"]:
                problems.append(f"{where}: prompt does not reconstruct from recorded inputs")
            else:
                n_prompts += 1
                leaked = [s for s in forbidden if s in prompt]
                if leaked:
                    problems.append(f"{where}: hidden-test content in prompt: {leaked}")
            if call["failure"] == "control_violation" or call["violations"]:
                problems.append(f"{where}: control violation {call['violations']}")
            if call["failure"] is None:
                models = call.get("models_used") or []
                want = expected_model[call["role"]]
                if len(models) != 1 or want not in models[0]:
                    problems.append(f"{where}: models_used {models}, expected only {want}")
            raw_path = call.get("raw_trace")
            if raw_path and (run_dir / raw_path).exists():
                raw = json.loads((run_dir / raw_path).read_text())
                problems += [f"{where}: {p}" for p in raw_trace_problems(raw["events"])]
            elif call["provider"] != "scripted":
                raw_missing += 1  # raw/ is gitignored; a fresh clone can only run checks 1, 2, 4, 5

    frozen_tasks = {tid: Task(tid, root / cfg["tasks_dir"] / tid).file_hashes()
                    for tid in meta["tasks"]}
    if frozen_tasks != meta["tasks"]:
        problems.append("task files changed since the run started")
    config_path = root / meta["config_path"]
    if sha256_text(config_path.read_text()) != meta["config_sha256"]:
        problems.append("config file changed since the run started")
    attempts = [json.loads(x) for x in (run_dir / "attempts.jsonl").read_text().splitlines() if x]
    if sorted(a["episode_id"] for a in attempts) != sorted(e["episode_id"] for e in episodes):
        problems.append("attempts.jsonl and episodes.jsonl disagree")

    return {"run_id": meta["run_id"], "episodes": len(episodes), "calls": n_calls,
            "prompts_reconstructed": n_prompts,
            "raw_traces_missing": raw_missing, "stopped": meta.get("stopped"),
            "problems": problems, "passed": not problems and not meta.get("stopped")}


def main() -> int:
    run_dir = Path(sys.argv[1])
    report = audit(run_dir, Path.cwd())
    (run_dir / "protocol_audit.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
