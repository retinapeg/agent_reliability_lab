"""If these fail, ground truth itself is wrong and no result can be trusted."""

import pytest

from agent_reliability.environments.coding.environment import (HIDDEN, VISIBLE, extract_solution,
                                                                load_tasks)
from agent_reliability.verifiers.pytest_verifier import parse_junit, run_tests

from .conftest import TASKS

TASK_IDS = [t.task_id for t in load_tasks(TASKS)]


def test_task_suite_size():
    assert len(TASK_IDS) >= 10


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_reference_passes_both_suites(task_id):
    ref = (TASKS / task_id / "reference.py").read_text()
    assert run_tests(ref, TASKS / task_id / VISIBLE)["passed"]
    assert run_tests(ref, TASKS / task_id / HIDDEN)["passed"]


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_starter_fails_visible(task_id):
    starter = (TASKS / task_id / "starter.py").read_text()
    r = run_tests(starter, TASKS / task_id / VISIBLE)
    assert not r["passed"] and r["failures"] + r["errors"] > 0


def test_hidden_catches_known_visible_only_bug():
    # lower() instead of casefold(), no NFKC: passes visible, must fail hidden.
    buggy = "def normalize_username(raw):\n    return '_'.join(raw.lower().split())\n"
    assert run_tests(buggy, TASKS / "normalize_username" / VISIBLE)["passed"]
    hid = run_tests(buggy, TASKS / "normalize_username" / HIDDEN)
    assert not hid["passed"] and "test_casefold_eszett" in hid["failed_tests"]


def test_syntax_error_is_failure_not_crash():
    r = run_tests("def broken(:\n", TASKS / "median" / VISIBLE)
    assert r["passed"] is False


def test_infinite_loop_times_out():
    r = run_tests("def median(v):\n    while True: pass\n", TASKS / "median" / VISIBLE, timeout_s=3)
    assert r["timed_out"] and not r["passed"]


def test_parse_junit_counts():
    xml = ('<testsuites><testsuite tests="3" failures="1" errors="1">'
           '<testcase name="a"/><testcase name="b"><failure/></testcase>'
           '<testcase name="c"><error/></testcase></testsuite></testsuites>')
    assert parse_junit(xml) == {"tests": 3, "failures": 1, "errors": 1, "failed_tests": ["b", "c"]}


def test_extract_solution_contract():
    assert extract_solution("```python\nx = 1\n```") == "x = 1\n"
    assert extract_solution("no code") is None
    assert extract_solution("```python\na=1\n```\n```python\nb=2\n```") is None
    assert extract_solution(None) is None
