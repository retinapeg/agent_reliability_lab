"""Separate model failure from system/protocol failure.

A wrong implementation is a *model* outcome and is graded. Everything here is a *system* or
*protocol* outcome: the call did not produce evidence about the model's ability, so it must be
counted and reported, never silently graded as a model failure or dropped.

Adapted from institutional-workbench (`providers.py`: unsuccessful-envelope and malformed-output
blocking; `runner.py`: timeouts) and agentic-physics-bench (`run_v2.py`: per-call control
violations for undeclared models, server-side tools and non-message iterations).
"""

from __future__ import annotations

# Call-level failure classes. None means the call succeeded.
TIMEOUT = "timeout"                    # process killed at the deadline
CLI_ERROR = "cli_error"                # non-zero exit, no usable envelope
PROVIDER_ERROR = "provider_error"      # envelope says error: auth, limits, overload
RATE_LIMITED = "rate_limited"          # provider reported a rejected rate-limit window
MALFORMED_OUTPUT = "malformed_output"  # call succeeded but reply violates the response contract
CONTROL_VIOLATION = "control_violation"  # the system that ran is not the system declared

RETRYABLE = {TIMEOUT, CLI_ERROR, PROVIDER_ERROR, RATE_LIMITED, MALFORMED_OUTPUT}
SYSTEM_FAILURES = {TIMEOUT, CLI_ERROR, PROVIDER_ERROR, RATE_LIMITED, CONTROL_VIOLATION}
PROTOCOL_FAILURES = {MALFORMED_OUTPUT}

_PROVIDER_MARKERS = ("overloaded", "rate limit", "rate_limit", "429", "529", "unauthorized",
                     "not logged in", "invalid api key", "credit", "usage limit", "quota")


def classify_claude_call(returncode: int | None, timed_out: bool, result_event: dict | None,
                         stderr: str) -> str | None:
    """Classify one Claude CLI call from its exit status, final `result` event and stderr."""
    if timed_out:
        return TIMEOUT
    text = (stderr + " " + str((result_event or {}).get("result", ""))).lower()
    if result_event is None:
        if any(m in text for m in _PROVIDER_MARKERS):
            return PROVIDER_ERROR
        return CLI_ERROR
    if result_event.get("is_error") or result_event.get("subtype") != "success":
        if "rate limit" in text or "usage limit" in text:
            return RATE_LIMITED
        return PROVIDER_ERROR
    if returncode not in (0, None):
        return CLI_ERROR
    return None


def claude_control_violations(summary: dict, expected_model: str | None) -> list[str]:
    """Per-call checks that the declared system ran (agentic-physics-bench V2 lesson).

    `expected_model` may be an alias (e.g. "sonnet"); in that case we require exactly one model
    whose ID contains the alias, rather than an exact ID match.
    """
    v: list[str] = []
    models = summary.get("models_used") or []
    if expected_model:
        match = [m for m in models if expected_model == m or expected_model in m]
        extra = [m for m in models if m not in match]
        if not match:
            v.append("expected_model_absent")
        if extra:
            v.append("unexpected_model_usage:" + ",".join(sorted(extra)))
    elif len(models) > 1:
        v.append("multiple_models:" + ",".join(sorted(models)))
    if summary.get("server_tool_uses"):
        v.append("server_tool_use:" + ",".join(sorted(set(summary["server_tool_uses"]))))
    if summary.get("tool_use_blocks"):
        v.append(f"native_tool_use:{summary['tool_use_blocks']}")
    odd = sorted(t for t in summary.get("iteration_types") or [] if t != "message")
    if odd:
        v.append("unexpected_iteration:" + ",".join(odd))
    return v


def classify_codex_events(events: list[dict], timed_out: bool, returncode: int | None) -> str | None:
    """Codex `exec --json` stream: failed turns are provider errors; any tool item is a violation."""
    if timed_out:
        return TIMEOUT
    for e in events:
        if e.get("type") in {"error", "turn.failed"}:
            msg = str(e).lower()
            return RATE_LIMITED if "rate" in msg or "usage limit" in msg else PROVIDER_ERROR
        item = e.get("item") or {}
        if item.get("type") == "error":
            return PROVIDER_ERROR
        if item and item.get("type") not in {"agent_message", "reasoning", "todo_list"}:
            return CONTROL_VIOLATION
    if not any(e.get("type") == "turn.completed" for e in events):
        return CLI_ERROR
    if returncode not in (0, None):
        return CLI_ERROR
    return None


def failure_kind(failure: str | None) -> str:
    """Bucket a call failure for reporting: ok / system / protocol."""
    if failure is None:
        return "ok"
    if failure in PROTOCOL_FAILURES:
        return "protocol"
    return "system"
