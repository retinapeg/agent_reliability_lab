"""End-to-end with scripted agents: episode records, schema, and every aggregation branch."""

import json

import pytest

from agent_reliability.agents.cli_agent import ScriptedAgent
from agent_reliability.analysis.summarize import analyze, compute_metrics
from agent_reliability.environments.coding.environment import load_tasks
from agent_reliability.runners.cross_review import Episode, EpisodeConfig
from agent_reliability.traces.store import RunStore, load_episodes, validate_episode

from .conftest import TASKS

BUGGY = "```python\ndef normalize_username(raw):\n    return '_'.join(raw.lower().split())\n```"
FIXED = "```python\n" + (TASKS / "normalize_username" / "reference.py").read_text() + "```"
REF_MEDIAN = "```python\n" + (TASKS / "median" / "reference.py").read_text() + "```"
WRONG_MEDIAN = "```python\ndef median(v):\n    return 0\n```"
FLAG = json.dumps({"verdict": "request_changes", "findings": [
    {"severity": "high", "category": "unicode", "description": "lower() not casefold()",
     "failing_input": "normalize_username('Straße')", "expected": "'strasse'", "confidence": 0.9}]})
FLAG_MEDIAN = FLAG.replace("unicode", "edge_case")
APPROVE = json.dumps({"verdict": "approve", "findings": []})


def run(tmp_path, task_id, coder_replies, review_replies, revision=True, rep=0, store=None):
    task = load_tasks(TASKS, [task_id])[0]
    store = store or RunStore(tmp_path, "test-run")
    coder = ScriptedAgent({"coder": coder_replies[:1], "reviser": coder_replies[1:]})
    reviewer = ScriptedAgent({"reviewer": review_replies})
    return Episode(task, coder, reviewer, store, EpisodeConfig(revision=revision), rep=rep).run(), store


def test_confirmed_flag_and_successful_revision(tmp_path):
    rec, _ = run(tmp_path, "normalize_username", [BUGGY, FIXED], [FLAG])
    validate_episode(rec)
    assert rec["visible"]["passed"] and not rec["hidden"]["passed"]
    assert rec["review"]["flagged"] and rec["review"]["actionable"]
    assert rec["review"]["blocking_categories"] == ["unicode"]
    assert rec["revision"]["hidden"]["passed"]
    assert "solution.py" in rec["coder"]["diff"]


def test_visible_failure_skips_review(tmp_path):
    rec, _ = run(tmp_path, "median", [WRONG_MEDIAN], [])
    assert not rec["visible"]["passed"] and rec["review"]["performed"] is False


def test_malformed_output_retried_then_protocol_failure(tmp_path):
    task = load_tasks(TASKS, ["median"])[0]
    coder = ScriptedAgent({"coder": ["no code here", "still none"]})
    rec = Episode(task, coder, ScriptedAgent({}), RunStore(tmp_path, "m"), EpisodeConfig()).run()
    assert rec["status"] == "protocol_failure"
    assert [c["failure"] for c in rec["calls"]] == ["malformed_output", "malformed_output"]


def test_provider_failure_is_system_failure_and_counted(tmp_path):
    task = load_tasks(TASKS, ["median"])[0]
    store = RunStore(tmp_path, "r")
    coder = ScriptedAgent({"coder": [None, REF_MEDIAN]})
    reviewer = ScriptedAgent({"reviewer": [None, None]})
    rec = Episode(task, coder, reviewer, store, EpisodeConfig()).run()
    assert [c["attempt"] for c in rec["calls"]] == [0, 1, 0, 1]
    assert rec["status"] == "system_failure" and rec["status_detail"] == "reviewer: provider_error"


def test_run_dir_never_overwritten(tmp_path):
    RunStore(tmp_path, "same")
    with pytest.raises(FileExistsError):
        RunStore(tmp_path, "same")


def test_aggregation_all_outcomes(tmp_path):
    store = RunStore(tmp_path, "agg")
    run(tmp_path, "normalize_username", [BUGGY, FIXED], [FLAG], store=store, rep=0)   # confirmed
    run(tmp_path, "normalize_username", [BUGGY], [APPROVE], store=store, rep=1)       # missed
    run(tmp_path, "median", [REF_MEDIAN, REF_MEDIAN], [FLAG_MEDIAN], store=store)     # unconfirmed
    run(tmp_path, "chunked", ["```python\n" + (TASKS / "chunked" / "reference.py").read_text()
                              + "```"], [APPROVE], store=store)                        # clean
    run(tmp_path, "format_cents", [WRONG_MEDIAN], [], store=store)                    # visible fail
    eps = load_episodes(store.dir)
    m = compute_metrics(eps)
    assert m["episodes"] == 5 and m["tasks"] == 4
    assert m["visible_pass"] == 4 and m["visible_pass_hidden_fail"] == 2
    assert m["review_outcomes"] == {"confirmed": 1, "unconfirmed": 1, "missed": 1, "clean_approve": 1}
    assert m["config_A"] == {"accepted": 4, "accepted_hidden_fail": 2}
    assert m["config_B"]["accepted"] == 2 and m["config_B"]["accepted_hidden_fail"] == 1
    assert m["config_C"]["fixed"] == 1 and m["config_C"]["regressed"] == 0
    assert m["config_C"]["accepted"] == 4 and m["config_C"]["accepted_hidden_fail"] == 1
    assert m["flag_categories"] == {"unicode": 1, "edge_case": 1}
    assert "bootstrap_95ci" not in m  # too few tasks


def test_analyze_renders_from_files_only(tmp_path):
    store = RunStore(tmp_path, "an")
    store.write_run_meta({"run_id": "an", "config": {
        "coder": {"provider": "scripted", "model": "s"}, "reviewer": {"provider": "scripted", "model": "s"},
        "flag_rule": {"severities": ["high"], "min_confidence": 0.6}}})
    run(tmp_path, "normalize_username", [BUGGY, FIXED], [FLAG], store=store)
    m, text = analyze(store.dir)
    assert "## 10. What can we NOT conclude?" in text and "(**confirmed**): 1" in text


def test_schema_rejects_bad_records():
    with pytest.raises(ValueError):
        validate_episode({"episode_id": "x"})
