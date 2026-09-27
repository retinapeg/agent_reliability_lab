from agent_reliability.analysis.protocol_checks import raw_trace_problems

RESULT = {"type": "result", "modelUsage": {"claude-sonnet-5": {}},
          "usage": {"server_tool_use": {"web_search_requests": 0, "web_fetch_requests": 0}}}


def test_zero_usage_counter_is_clean():
    init = {"type": "system", "subtype": "init", "tools": [], "mcp_servers": []}
    assert raw_trace_problems([init, RESULT]) == []


def test_detects_server_tool_advisor_and_second_model():
    used = dict(RESULT, usage={"server_tool_use": {"web_search_requests": 1}},
                modelUsage={"claude-sonnet-5": {}, "claude-fable-5-1": {}})
    advisor = {"type": "assistant", "message": {"content": [{"type": "advisor_tool_result"}]}}
    tool = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash"}]}}
    problems = raw_trace_problems([advisor, tool, used])
    assert any("advisor_tool_result block" in p for p in problems)
    assert any("tool_use block" in p for p in problems)
    assert any("non-zero server tool usage" in p for p in problems)
    assert any("modelUsage has" in p for p in problems)
