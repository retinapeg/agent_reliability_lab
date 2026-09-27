"""Agents: one bounded, tool-less model call per step, through a local CLI.

Every call runs in an empty temporary directory with a sanitized environment, no native tools,
no MCP servers and no saved session. The agent can only *return text*; the harness decides what
to do with it. This is a deliberate simplification of agent-workflow-orchestrator's tool-using
worktree agents (see docs/architecture.md, "Shortcuts").

CLI flags adapted from institutional-workbench `providers.py` and agentic-physics-bench
`models.py`; the advisor switch and usage-based model checks from agentic-physics-bench
`run_v2.py`; the sanitized environment from agent-workflow-orchestrator `providers/cli.py`.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import Protocol

from ..reliability import failures

# Only these variables reach the child. In particular nothing from a parent Claude Code session.
_ENV_KEEP = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TERM", "TMPDIR", "SHELL")
# The Claude CLI can consult a second model through a server-side advisor tool even with
# --tools "" (found by agentic-physics-bench on 2026-09-23). Disable it and check usage per call.
_ENV_CONTROLS = {"CLAUDE_CODE_DISABLE_ADVISOR_TOOL": "1"}


def sanitized_env() -> dict[str, str]:
    env = {k: os.environ[k] for k in _ENV_KEEP if k in os.environ}
    env.update(_ENV_CONTROLS)
    return env


@dataclass
class CallRecord:
    """Everything recorded about one model call. `raw` goes to the gitignored raw trace only."""

    role: str
    provider: str
    model: str
    prompt: str
    text: str | None
    elapsed_s: float
    returncode: int | None
    timed_out: bool
    failure: str | None
    violations: list[str] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    list_cost_usd: float | None = None  # CLI list-price metadata, not a subscription charge
    models_used: list[str] = field(default_factory=list)
    cli_version: str | None = None
    stderr_head: str | None = None
    raw: dict = field(default_factory=dict)

    def summary(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "raw"}
        return d


class Agent(Protocol):
    provider: str
    model: str

    def call(self, role: str, prompt: str) -> CallRecord: ...


def _run(argv: list[str], prompt: str, timeout_s: float) -> tuple[int | None, str, str, bool, float]:
    with tempfile.TemporaryDirectory(prefix="arl-call-") as cwd:
        started = time.monotonic()
        out: tuple[int | None, str, str, bool]
        try:
            proc = subprocess.run(argv, input=prompt, capture_output=True, text=True, cwd=cwd,
                                  env=sanitized_env(), timeout=timeout_s)
            out = (proc.returncode, proc.stdout, proc.stderr, False)
        except subprocess.TimeoutExpired as exc:
            so = exc.stdout or ""
            out = (None, so.decode() if isinstance(so, bytes) else so, f"timeout after {timeout_s}s",
                   True)
        return out[0], out[1], out[2], out[3], round(time.monotonic() - started, 3)


def summarize_claude_events(events: list[dict]) -> dict:
    """Reviewed fields from a Claude CLI stream-json event list (agentic-physics-bench V2)."""
    s: dict = {"cli_version": None, "models_used": [], "server_tool_uses": [], "tool_use_blocks": 0,
               "iteration_types": [], "result": None, "usage": {}, "cost": None}
    for e in events:
        kind = e.get("type")
        if kind == "system" and e.get("subtype") == "init":
            s["cli_version"] = e.get("claude_code_version")
        elif kind == "assistant":
            for c in (e.get("message") or {}).get("content", []):
                if c.get("type") == "tool_use":
                    s["tool_use_blocks"] += 1
                elif c.get("type") == "server_tool_use":
                    s["server_tool_uses"].append(str(c.get("name")))
                elif c.get("type") == "advisor_tool_result":
                    s["server_tool_uses"].append("advisor")
        elif kind == "result":
            s["result"] = e
            usage = e.get("usage") or {}
            s["usage"] = {k: usage.get(k) for k in ("input_tokens", "cache_creation_input_tokens",
                                                     "cache_read_input_tokens", "output_tokens")}
            s["models_used"] = sorted((e.get("modelUsage") or {}).keys())
            s["iteration_types"] = sorted({str(i.get("type")) for i in usage.get("iterations") or []})
            s["cost"] = e.get("total_cost_usd")
    return s


@dataclass
class ClaudeCliAgent:
    model: str
    timeout_s: float = 300
    effort: str | None = None
    provider: str = "claude_cli"

    def argv(self) -> list[str]:
        argv = ["claude", "--print", "--model", self.model, "--tools", "", "--safe-mode",
                "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
                "--no-session-persistence", "--output-format", "stream-json", "--verbose"]
        if self.effort:
            argv += ["--effort", self.effort]
        return argv

    def call(self, role: str, prompt: str) -> CallRecord:
        argv = self.argv()
        rc, stdout, stderr, timed_out, elapsed = _run(argv, prompt, self.timeout_s)
        events, non_json = [], []
        for line in stdout.splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                non_json.append(line)
        s = summarize_claude_events(events)
        failure = failures.classify_claude_call(rc, timed_out, s["result"], stderr)
        violations = [] if failure else failures.claude_control_violations(s, self.model)
        if violations:
            failure = failures.CONTROL_VIOLATION
        text = (s["result"] or {}).get("result") if failure is None else None
        return CallRecord(role=role, provider=self.provider, model=self.model, prompt=prompt,
                          text=text, elapsed_s=elapsed, returncode=rc, timed_out=timed_out,
                          failure=failure, violations=violations, usage=s["usage"],
                          list_cost_usd=s["cost"], models_used=s["models_used"],
                          cli_version=s["cli_version"],
                          stderr_head=stderr.strip().splitlines()[0][:200] if stderr.strip() else None,
                          raw={"argv": argv, "events": events, "non_json_stdout": non_json,
                               "stderr": stderr})


@dataclass
class CodexCliAgent:
    """Codex CLI, read-only, with tool features disabled (institutional-workbench flags)."""

    model: str
    timeout_s: float = 300
    reasoning_effort: str = "medium"
    provider: str = "codex_cli"

    def argv(self) -> list[str]:
        argv = ["codex", "exec", "--ignore-user-config", "--ignore-rules", "--ephemeral",
                "--skip-git-repo-check", "--sandbox", "read-only", "--json",
                "-c", 'approval_policy="never"', "-c", 'web_search="disabled"',
                "-c", "project_doc_max_bytes=0", "-c", "suppress_unstable_features_warning=true",
                "-c", f'model_reasoning_effort="{self.reasoning_effort}"', "--model", self.model]
        for feature in ("hooks", "plugins", "apps", "shell_tool", "unified_exec", "multi_agent",
                        "multi_agent_v2", "browser_use", "in_app_browser", "image_generation",
                        "view_image", "memories", "skill_search", "sleep_tool", "js_repl",
                        "tool_suggest"):
            argv += ["--disable", feature]
        return argv + ["--enable", "skip_host_skill_discovery", "-"]

    def call(self, role: str, prompt: str) -> CallRecord:
        argv = self.argv()
        rc, stdout, stderr, timed_out, elapsed = _run(argv, prompt, self.timeout_s)
        events = []
        for line in stdout.splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        failure = failures.classify_codex_events(events, timed_out, rc)
        messages = [e["item"].get("text", "") for e in events if e.get("type") == "item.completed"
                    and (e.get("item") or {}).get("type") == "agent_message"]
        usage = next((e.get("usage") or {} for e in events if e.get("type") == "turn.completed"), {})
        if failure is None and len(messages) != 1:
            failure = failures.MALFORMED_OUTPUT
        return CallRecord(role=role, provider=self.provider, model=self.model, prompt=prompt,
                          text=messages[0] if failure is None else None, elapsed_s=elapsed,
                          returncode=rc, timed_out=timed_out, failure=failure,
                          violations=["tool_item"] if failure == failures.CONTROL_VIOLATION else [],
                          usage=usage, models_used=[self.model],
                          stderr_head=stderr.strip().splitlines()[0][:200] if stderr.strip() else None,
                          raw={"argv": argv, "events": events, "stderr": stderr})


@dataclass
class ScriptedAgent:
    """Deterministic offline agent for tests (agent-workflow-orchestrator `providers/scripted.py`).

    `replies` maps role -> list of reply texts consumed in order; a `None` reply simulates a
    provider failure.
    """

    replies: dict[str, list[str | None]]
    model: str = "scripted"
    provider: str = "scripted"

    def call(self, role: str, prompt: str) -> CallRecord:
        text = self.replies[role].pop(0)
        failure = failures.PROVIDER_ERROR if text is None else None
        return CallRecord(role=role, provider=self.provider, model=self.model, prompt=prompt,
                          text=text, elapsed_s=0.0, returncode=0, timed_out=False, failure=failure,
                          usage={"input_tokens": len(prompt) // 4,
                                 "output_tokens": len(text or "") // 4})


def make_agent(spec: dict) -> Agent:
    provider = spec["provider"]
    if provider == "claude_cli":
        return ClaudeCliAgent(model=spec["model"], timeout_s=spec.get("timeout_s", 300),
                              effort=spec.get("effort"))
    if provider == "codex_cli":
        return CodexCliAgent(model=spec["model"], timeout_s=spec.get("timeout_s", 300))
    raise ValueError(f"unknown provider {provider!r}")
