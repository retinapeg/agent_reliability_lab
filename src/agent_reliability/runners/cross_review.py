"""One experiment episode per task: code -> verify -> (review -> revise) -> hidden-test ground truth.

Configurations are evaluated *paired* on the same coder output:

  A  accept if the visible acceptance tests pass
  B  accept if visible tests pass AND the independent review does not flag the candidate
  C  if B flags, one bounded revision from the review findings; accept if visible tests still pass

The hidden tests are run on every candidate but their results never reach an agent; they are the
ground truth the analysis uses to ask whether review flags correspond to real defects.

Control flow adapted from agent-workflow-orchestrator `orchestrator.py` (implement -> review ->
bounded revise -> fresh re-evaluation) and reduced to a single engineer per task.
"""

from __future__ import annotations

import datetime as dt
import json
import platform
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..agents.cli_agent import Agent, CallRecord
from ..environments.coding.environment import HIDDEN, VISIBLE, Task, Workspace, extract_solution
from ..reliability import failures
from ..review.reviewer import (FlagRule, MalformedReview, ReviewResult, build_review_prompt,
                               build_revision_prompt, parse_review)
from ..traces.store import SCHEMA_VERSION, RunStore, redact
from ..verifiers.pytest_verifier import run_tests


class BatchStopped(RuntimeError):
    """A control violation: the system that ran was not the system declared. Stop the batch."""


def build_coder_prompt(task: Task) -> str:
    return f"""Implement the following specification in Python 3.11 using only the standard library.

SPECIFICATION:
{task.spec}

STARTER solution.py:
```python
{task.starter}
```

ACCEPTANCE TESTS (test_visible.py, run with pytest against your solution.py):
```python
{task.visible_tests}
```

Your code is accepted when it satisfies the specification. Return the complete solution.py as
exactly one ```python fenced code block and nothing else."""


TOOLS = ("read_file", "write_solution", "run_tests", "finish")
_ACTION = re.compile(r"^ACTION:[ \t]*(\w+)[ \t]*(.*)$", re.MULTILINE)
OBSERVATION_LIMIT = 2000


def parse_action(text: str | None) -> tuple[str, str] | None:
    """Exactly one `ACTION:` line naming a known tool, or None (a protocol failure)."""
    if not text:
        return None
    found = _ACTION.findall(text)
    if len(found) != 1 or found[0][0] not in TOOLS:
        return None
    tool, arg = found[0][0], found[0][1].strip()
    if tool == "read_file" and not arg:
        return None
    if tool == "write_solution" and extract_solution(text) is None:
        return None
    return tool, arg


def build_agent_prompt(task: Task, steps: list[dict], max_steps: int) -> str:
    """Prompt for one tool-loop step. Calls are stateless: the harness replays the transcript.

    A pure function of the task and the recorded steps, so the protocol audit can rebuild every
    step prompt and match its hash.
    """
    transcript = "".join(f"\n[step {s['step'] + 1}] YOU:\n{s['reply']}\nOBSERVATION:\n"
                         f"{s['observation']}\n" for s in steps) or "\n(nothing yet)\n"
    return f"""You are a coding agent. Implement the specification below in Python 3.11 using only the
standard library. Your workspace contains two files: solution.py (a stub) and test_visible.py
(the acceptance tests).

SPECIFICATION:
{task.spec}

Each turn, reply with exactly one action line and nothing that is not needed for it:
ACTION: read_file solution.py        (or test_visible.py; no other file exists for you)
ACTION: write_solution               (followed by exactly one ```python fenced block containing
                                      the complete new solution.py)
ACTION: run_tests                    (runs test_visible.py against the current solution.py)
ACTION: finish                       (submit the current solution.py)

You have {max_steps} steps in total and {max_steps - len(steps)} left. When they run out, the
current solution.py is submitted as it is. Your code is accepted when it satisfies the specification.

TRANSCRIPT SO FAR:
{transcript}
Reply with your next action."""


@dataclass
class EpisodeConfig:
    max_retries: int = 1
    revision: bool = True
    flag_rule: FlagRule = FlagRule()
    verify_timeout_s: float = 60
    coder_mode: str = "one_shot"  # or "tool_loop"
    max_tool_steps: int = 5


class Episode:
    def __init__(self, task: Task, coder: Agent, reviewer: Agent, store: RunStore,
                 cfg: EpisodeConfig, rep: int = 0):
        self.task, self.coder, self.reviewer, self.store, self.cfg = task, coder, reviewer, store, cfg
        self.rep = rep
        self.episode_id = f"{task.task_id}-r{rep}"
        self.calls: list[dict] = []

    # -- model calls with bounded, counted retries ------------------------------------------
    def _call(self, agent: Agent, role: str, prompt: str, accept,
              extra: dict | None = None) -> tuple[CallRecord, object, int]:
        """Call until `accept(text)` returns a non-None value or retries run out.

        Returns (last record, accepted value or None, retries used). A control violation is never
        retried: it invalidates the batch.
        """
        value, rec = None, None
        for attempt in range(self.cfg.max_retries + 1):
            rec = agent.call(role, prompt)
            if rec.failure is None:
                value = accept(rec.text)
                if value is None:
                    rec.failure = failures.MALFORMED_OUTPUT
            raw_path = self.store.write_raw(self.episode_id, len(self.calls), role, rec.raw) \
                if rec.raw else None
            summary = rec.summary()
            summary.update(attempt=attempt, raw_trace=raw_path, prompt_sha256=_sha(rec.prompt),
                           text=redact(rec.text), stderr_head=redact(rec.stderr_head),
                           failure_kind=failures.failure_kind(rec.failure), **(extra or {}))
            summary.pop("prompt")
            self.calls.append(summary)
            if rec.failure == failures.CONTROL_VIOLATION:
                raise BatchStopped(f"{self.episode_id} {role}: {rec.violations}")
            if value is not None or rec.failure not in failures.RETRYABLE:
                return rec, value, attempt
        assert rec is not None
        return rec, value, self.cfg.max_retries

    # -- bounded tool loop for the coder ------------------------------------------------------
    def _tool_loop(self, ws: Workspace) -> tuple[CallRecord, str | None, int, list[dict]]:
        """At most `max_tool_steps` model calls, one action each. Returns (last call, final
        solution.py or None on a system/protocol failure, retries used, recorded steps).

        The model still has no native tools: it names an action in text and the harness executes
        it. The three tools can only read the two workspace files, replace solution.py and run the
        VISIBLE tests. Nothing here references the hidden tests.
        """
        steps: list[dict] = []
        retries, call = 0, None
        for k in range(self.cfg.max_tool_steps):
            prompt = build_agent_prompt(self.task, steps, self.cfg.max_tool_steps)
            call, action, used = self._call(self.coder, "coder", prompt, parse_action,
                                            extra={"step": k})
            retries += used
            if action is None:
                return call, None, retries, steps
            tool, arg = action  # type: ignore[misc]
            reply = redact(call.text) or ""
            observation = self._execute(ws, tool, arg, reply)
            steps.append({"step": k, "tool": tool, "arg": arg, "reply": reply,
                          "observation": observation, "call_index": len(self.calls) - 1})
            if tool == "finish":
                break
        assert call is not None
        return call, ws.read("solution.py"), retries, steps

    def _execute(self, ws: Workspace, tool: str, arg: str, reply: str) -> str:
        if tool == "read_file":
            try:
                out = ws.read(arg)
            except PermissionError:
                out = f"ERROR: only {' and '.join(ws.READABLE)} can be read."
        elif tool == "write_solution":
            code = extract_solution(reply)
            assert code is not None  # guaranteed by parse_action
            ws.write_solution(code)
            out = f"solution.py written ({len(code.splitlines())} lines)."
        elif tool == "run_tests":
            r = run_tests(ws.read("solution.py"), self.task.root / VISIBLE,
                          self.cfg.verify_timeout_s)
            out = (f"{r['tests']} tests, {r['failures']} failures, {r['errors']} errors"
                   f"{' (timed out)' if r['timed_out'] else ''}\n{r['output_tail']}")
        else:
            out = "Submitted."
        return (redact(out) or "")[:OBSERVATION_LIMIT]

    def _verify(self, code: str) -> tuple[dict, dict]:
        vis = run_tests(code, self.task.root / VISIBLE, self.cfg.verify_timeout_s)
        hid = run_tests(code, self.task.root / HIDDEN, self.cfg.verify_timeout_s)
        return vis, hid

    def run(self) -> dict:
        started = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        self.store.append("attempts.jsonl", {"episode_id": self.episode_id, "task_id":
                                             self.task.task_id, "started_at": started})
        rec: dict = {"schema": SCHEMA_VERSION, "run_id": self.store.run_id,
                     "episode_id": self.episode_id, "task_id": self.task.task_id,
                     "rep": self.rep, "started_at": started, "status": "complete", "status_detail": None,
                     "coder": None, "visible": None, "hidden": None, "review": None,
                     "revision": None}
        try:
            self._run_into(rec)
        finally:
            rec["calls"] = self.calls
            rec["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            self.store.append("episodes.jsonl", rec)
        return rec

    def _run_into(self, rec: dict) -> None:
        with tempfile.TemporaryDirectory(prefix="arl-ws-") as tmp:
            ws = Workspace(self.task, Path(tmp) / "ws")
            if self.cfg.coder_mode == "tool_loop":
                call, code, retries, steps = self._tool_loop(ws)
            else:
                call, code, retries = self._call(self.coder, "coder",
                                                 build_coder_prompt(self.task), extract_solution)
                steps = None
            rec["coder"] = {"provider": self.coder.provider, "model": self.coder.model,
                            "retries": retries, "failure": call.failure,
                            "mode": self.cfg.coder_mode}
            if steps is not None:
                rec["coder"].update(steps=steps, max_tool_steps=self.cfg.max_tool_steps)
            if code is None:
                rec["status"] = _status_for(call.failure)
                rec["status_detail"] = f"coder: {call.failure}"
                return
            assert isinstance(code, str)
            rec["coder"].update(ws.commit_candidate(code, "candidate"),
                                baseline_sha=ws.baseline_sha, code=code)
            rec["visible"], rec["hidden"] = self._verify(code)
            if not rec["visible"]["passed"]:
                rec["review"] = {"performed": False, "reason": "visible tests failed (A rejects)"}
                return

            prompt = build_review_prompt(self.task.spec, code, self.task.visible_tests,
                                         rec["visible"])
            call, review, retries = self._call(self.reviewer, "reviewer", prompt, _parse_or_none)
            if review is None:
                rec["status"] = _status_for(call.failure)
                rec["status_detail"] = f"reviewer: {call.failure}"
                rec["review"] = {"performed": False, "reason": call.failure, "retries": retries}
                return
            assert isinstance(review, ReviewResult)
            rule = self.cfg.flag_rule
            blocking = review.blocking(rule)
            rec["review"] = {"performed": True, "provider": self.reviewer.provider,
                             "model": self.reviewer.model, "retries": retries,
                             "verdict": review.verdict, "flagged": review.flagged(rule),
                             "findings": [f.__dict__ for f in review.findings],
                             "blocking_categories": sorted({f.category for f in blocking}),
                             "actionable": bool(blocking) and all(f.failing_input.strip()
                                                                  for f in blocking)}
            if not (self.cfg.revision and rec["review"]["flagged"]):
                rec["revision"] = {"triggered": False}
                return
            call, new_code, retries = self._call(
                self.coder, "reviser", build_revision_prompt(self.task.spec, code, blocking),
                extract_solution)
            rec["revision"] = {"triggered": True, "retries": retries, "failure": call.failure}
            if new_code is None:
                rec["status"] = _status_for(call.failure)
                rec["status_detail"] = f"reviser: {call.failure}"
                return
            assert isinstance(new_code, str)
            vis, hid = self._verify(new_code)
            rec["revision"].update(ws.commit_candidate(new_code, "revision"), code=new_code,
                                   visible=vis, hidden=hid)


def _parse_or_none(text: str | None) -> ReviewResult | None:
    try:
        return parse_review(text)
    except MalformedReview:
        return None


def _status_for(failure: str | None) -> str:
    return "protocol_failure" if failure in failures.PROTOCOL_FAILURES else "system_failure"


def _sha(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode()).hexdigest()


def environment_facts() -> dict:
    def version(argv: list[str]) -> str | None:
        try:
            return subprocess.run(argv, capture_output=True, text=True, timeout=20).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            return None

    return {"python": platform.python_version(), "platform": platform.platform(),
            "claude_cli": version(["claude", "--version"]),
            "codex_cli": version(["codex", "--version"]),
            "lab_git_sha": version(["git", "rev-parse", "HEAD"]),
            "lab_git_dirty": bool(version(["git", "status", "--porcelain"]))}


def dumps(obj: object) -> str:
    return json.dumps(obj, indent=2, sort_keys=True)
