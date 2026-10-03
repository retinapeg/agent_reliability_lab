"""Tool-loop coder: bounded steps, allow-listed reads, visible tests only, full trace, audit."""

import json
from pathlib import Path

from agent_reliability.agents.cli_agent import ScriptedAgent
from agent_reliability.analysis.protocol_checks import audit
from agent_reliability.environments.coding.environment import load_tasks
from agent_reliability.runners.cross_review import (Episode, EpisodeConfig, build_agent_prompt,
                                                    parse_action)
from agent_reliability.traces.store import RunStore, sha256_text, validate_episode

from .conftest import ROOT, TASKS

REF = (TASKS / "median" / "reference.py").read_text()
WRITE_BAD = "ACTION: write_solution\n```python\ndef median(values):\n    return 0\n```"
WRITE_GOOD = "ACTION: write_solution\n```python\n" + REF + "```"
APPROVE = json.dumps({"verdict": "approve", "findings": []})
CFG = EpisodeConfig(coder_mode="tool_loop", max_tool_steps=5)


def episode(tmp_path, coder_replies, reviewer_replies=(APPROVE,), cfg=CFG, run_id="tl"):
    task = load_tasks(TASKS, ["median"])[0]
    store = RunStore(tmp_path, run_id)
    rec = Episode(task, ScriptedAgent({"coder": list(coder_replies)}),
                  ScriptedAgent({"reviewer": list(reviewer_replies)}), store, cfg).run()
    return rec, store, task


def test_parse_action():
    assert parse_action("ACTION: run_tests") == ("run_tests", "")
    assert parse_action("thinking...\nACTION: read_file test_visible.py") == ("read_file",
                                                                              "test_visible.py")
    assert parse_action(WRITE_GOOD)[0] == "write_solution"
    for bad in [None, "", "run the tests", "ACTION: read_file", "ACTION: write_solution",
                "ACTION: shell ls", "ACTION: run_tests\nACTION: finish"]:
        assert parse_action(bad) is None


def test_loop_iterates_on_visible_test_feedback(tmp_path):
    rec, store, _ = episode(tmp_path, ["ACTION: read_file test_visible.py", WRITE_BAD,
                                       "ACTION: run_tests", WRITE_GOOD, "ACTION: finish"])
    validate_episode(rec)
    steps = rec["coder"]["steps"]
    assert [s["tool"] for s in steps] == ["read_file", "write_solution", "run_tests",
                                          "write_solution", "finish"]
    assert "def test_odd_unsorted" in steps[0]["observation"]
    assert steps[2]["observation"].startswith("3 tests, 3 failures")
    # Final verdict comes from deterministic verification of the frozen file, not from the model.
    assert rec["visible"]["passed"] and rec["hidden"]["passed"]
    assert rec["review"]["performed"] and rec["coder"]["mode"] == "tool_loop"
    # Every model call is traced with its step.
    assert [c.get("step") for c in rec["calls"] if c["role"] == "coder"] == [0, 1, 2, 3, 4]


def test_step_limit_is_hard(tmp_path):
    rec, _, _ = episode(tmp_path, ["ACTION: run_tests"] * 9, reviewer_replies=())
    assert len(rec["coder"]["steps"]) == 5 and len(rec["calls"]) == 5
    assert not rec["visible"]["passed"]  # stub submitted; A rejects; no review
    assert rec["review"]["performed"] is False


def test_hidden_tests_unreachable(tmp_path):
    asks = ["ACTION: read_file test_hidden.py", "ACTION: read_file ../median/test_hidden.py",
            "ACTION: read_file reference.py", WRITE_GOOD, "ACTION: finish"]
    rec, store, _ = episode(tmp_path, asks)
    hidden = (TASKS / "median" / "test_hidden.py").read_text()
    for s in rec["coder"]["steps"][:3]:
        assert s["observation"].startswith("ERROR")
    blob = json.dumps(rec["coder"]["steps"])
    assert "test_no_mutation" not in blob and "def median(values) -> float:\n    if len" not in blob
    assert hidden not in blob
    # The audit reports the attempts rather than passing silently.
    store.write_run_meta(_meta(store))
    assert any("outside the allow-list" in p for p in audit(store.dir, ROOT)["problems"])


def test_malformed_action_is_protocol_failure(tmp_path):
    rec, _, _ = episode(tmp_path, ["I will now run the tests", "sure, running"], ())
    assert rec["status"] == "protocol_failure" and rec["status_detail"] == "coder: malformed_output"
    assert [c["attempt"] for c in rec["calls"]] == [0, 1]


def test_prompts_reconstruct_and_audit_passes(tmp_path):
    rec, store, task = episode(tmp_path, [WRITE_GOOD, "ACTION: run_tests", "ACTION: finish"])
    steps = rec["coder"]["steps"]
    for call in (c for c in rec["calls"] if c["role"] == "coder"):
        prompt = build_agent_prompt(task, steps[:call["step"]], 5)
        assert sha256_text(prompt) == call["prompt_sha256"]
        assert "test_hidden" not in prompt
    store.write_run_meta(_meta(store))
    report = audit(store.dir, ROOT)
    assert report["problems"] == [] and report["prompts_reconstructed"] == 4


def _meta(store):
    config = "configs/cross_review_tool_loop_v1.json"
    task = load_tasks(TASKS, ["median"])[0]
    return {"run_id": store.run_id, "config_path": config,
            "config_sha256": sha256_text((ROOT / config).read_text()),
            "config": json.loads((ROOT / config).read_text()),
            "tasks": {"median": task.file_hashes()}}
