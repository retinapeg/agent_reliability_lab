from agent_reliability.agents.cli_agent import sanitized_env, summarize_claude_events
from agent_reliability.reliability import failures as F

OK = {"type": "result", "subtype": "success", "is_error": False, "result": "hi"}


def test_claude_classification():
    assert F.classify_claude_call(0, False, OK, "") is None
    assert F.classify_claude_call(None, True, None, "") == F.TIMEOUT
    assert F.classify_claude_call(1, False, None, "boom") == F.CLI_ERROR
    assert F.classify_claude_call(1, False, None, "Error: 529 overloaded") == F.PROVIDER_ERROR
    err = dict(OK, subtype="error_during_execution", is_error=True, result="usage limit reached")
    assert F.classify_claude_call(1, False, err, "") == F.RATE_LIMITED


def test_control_violations_detect_second_model_and_advisor():
    events = [
        {"type": "system", "subtype": "init", "claude_code_version": "2.1.283"},
        {"type": "assistant", "message": {"content": [{"type": "advisor_tool_result"}]}},
        {"type": "result", **OK, "modelUsage": {"claude-sonnet-5": {}, "claude-fable-5-1": {}},
         "usage": {"iterations": [{"type": "message"}, {"type": "advisor_message"}]}},
    ]
    s = summarize_claude_events(events)
    v = F.claude_control_violations(s, "sonnet")
    assert any(x.startswith("unexpected_model_usage:claude-fable-5-1") for x in v)
    assert "server_tool_use:advisor" in v
    assert any(x.startswith("unexpected_iteration") for x in v)


def test_clean_call_has_no_violations():
    s = summarize_claude_events([{"type": "result", **OK, "modelUsage": {"claude-haiku-4-5": {}},
                                  "usage": {"iterations": [{"type": "message"}]}}])
    assert F.claude_control_violations(s, "haiku") == []
    assert F.claude_control_violations(s, "sonnet") == ["expected_model_absent",
                                                        "unexpected_model_usage:claude-haiku-4-5"]


def test_codex_classification():
    done = {"type": "turn.completed", "usage": {}}
    msg = {"type": "item.completed", "item": {"type": "agent_message", "text": "x"}}
    assert F.classify_codex_events([msg, done], False, 0) is None
    assert F.classify_codex_events([{"type": "item.started", "item": {"type": "command_execution"}}],
                                   False, 0) == F.CONTROL_VIOLATION
    assert F.classify_codex_events([{"type": "turn.failed"}], False, 1) == F.PROVIDER_ERROR
    assert F.classify_codex_events([msg], False, 0) == F.CLI_ERROR


def test_failure_kinds():
    assert F.failure_kind(None) == "ok"
    assert F.failure_kind(F.MALFORMED_OUTPUT) == "protocol"
    assert F.failure_kind(F.TIMEOUT) == "system"


def test_sanitized_env_drops_parent_session(monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    env = sanitized_env()
    assert "CLAUDECODE" not in env and "ANTHROPIC_API_KEY" not in env
    assert env["CLAUDE_CODE_DISABLE_ADVISOR_TOOL"] == "1"
