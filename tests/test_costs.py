"""Costs are derived from raw tokens and a dated price table; an unknown cost is never $0."""

from agent_reliability.agents.cli_agent import summarize_claude_events
from agent_reliability.analysis.summarize import call_cost, compute_metrics, render_summary
from agent_reliability.pricing import PriceTable, load_price_table
from agent_reliability.traces.store import RunStore, load_episodes

from .test_pipeline_and_aggregation import FLAG_MEDIAN, REF_MEDIAN, run

PRICES = """
version = "test-1"
[models."gpt-test"]
input_per_mtok = 2
cache_read_per_mtok = 0.20
cache_write_per_mtok = 2.50
output_per_mtok = 10
reasoning = "included_in_output"
source = "https://example.invalid"
retrieved = "2026-10-03"
[models."claude-test"]
input_per_mtok = 2
cache_read_per_mtok = 0.20
cache_write_per_mtok = 2.50
cache_write_1h_per_mtok = 4
output_per_mtok = 10
source = "https://example.invalid"
retrieved = "2026-10-03"
"""
META = {"run_id": "costs", "models_observed": ["claude-test", "gpt-test"],
        "config": {"coder": {"provider": "codex_cli", "model": "gpt-test"},
                   "reviewer": {"provider": "claude_cli", "model": "claude-test"},
                   "flag_rule": {"severities": ["high"], "min_confidence": 0.6}}}
# Codex reports no cost. Usage keys as codex-cli emits them in turn.completed.
CODEX = {"provider": "codex_cli", "model": "gpt-test", "models_used": ["gpt-test"],
         "list_cost_usd": None,
         "usage": {"input_tokens": 12717, "cached_input_tokens": 6912,
                   "cache_write_input_tokens": 0, "output_tokens": 189,
                   "reasoning_output_tokens": 96}}
CODEX_USD = 0.014882  # (12717-6912)*2 + 6912*0.2 + 189*10 per million
# A real reviewer call (claude 2.1.288, 2026-10-03): the CLI reported 0.0247516 for these tokens.
CLAUDE = {"provider": "claude_cli", "model": "claude-test", "models_used": ["claude-test"],
          "list_cost_usd": 0.0247516,
          "usage": {"input_tokens": 2, "cache_creation_input_tokens": 3051,
                    "cache_read_input_tokens": 518, "output_tokens": 1244,
                    "cache_creation": {"ephemeral_5m_input_tokens": 0,
                                       "ephemeral_1h_input_tokens": 3051}}}


def table(tmp_path) -> PriceTable:
    path = tmp_path / "pricing.toml"
    path.write_text(PRICES)
    return load_price_table(path)


def episodes(tmp_path, by_role: dict) -> list[dict]:
    """Two scripted median episodes (coder, reviewer, reviser each), calls rewritten per role."""
    store = RunStore(tmp_path, "costs")
    for rep in (0, 1):
        run(tmp_path, "median", [REF_MEDIAN, REF_MEDIAN], [FLAG_MEDIAN], store=store, rep=rep)
    eps = load_episodes(store.dir)
    seen: dict[str, int] = {}
    for e in eps:
        for c in e["calls"]:
            variants = by_role[c["role"]]
            c.update(variants[seen.get(c["role"], 0) % len(variants)])
            seen[c["role"]] = seen.get(c["role"], 0) + 1
    return eps


def cost_line(text: str) -> str:
    return next(line for line in text.splitlines() if line.startswith("- Cost, "))


def test_codex_call_without_cost_is_estimated_when_priced_and_null_when_not(tmp_path):
    priced = call_cost(CODEX, table(tmp_path))
    assert priced["cost_usd"] == CODEX_USD and priced["cost_source"] == "api_estimate"
    unpriced = call_cost(CODEX, PriceTable({}))
    assert unpriced["cost_usd"] is None and unpriced["cost_source"] == "unpriced"
    assert "'gpt-test' not in the pricing file" in unpriced["unpriced_reason"]
    assert call_cost(CLAUDE, PriceTable({}))["cost_source"] == "cli_reported"


def test_roles_show_cost_with_coverage(tmp_path):
    eps = episodes(tmp_path, {"coder": [CODEX], "reviewer": [CLAUDE], "reviser": [CODEX]})
    m = compute_metrics(eps, table(tmp_path))
    assert m["overhead"]["coder_cost"] == {"cost_usd": round(2 * CODEX_USD, 6),
                                           "calls_priced": 2, "calls": 2}
    assert m["overhead"]["oversight_cost"] == {
        "cost_usd": round(2 * 0.024752 + 2 * CODEX_USD, 6), "calls_priced": 4, "calls": 4}
    assert m["cost_by_role"]["reviewer"]["cost_sources"] == {
        "cli_reported": 2, "api_estimate": 0, "unpriced": 0}
    assert m["pricing"]["version"] == "test-1" and len(m["pricing"]["sha256"]) == 64
    assert {c["cost_source"] for c in m["call_costs"]} == {"cli_reported", "api_estimate"}
    line = cost_line(render_summary(META, m))
    assert "coder $0.0298 (2/2 calls priced); review + revision $0.0793 (4/4 calls priced)" in line
    assert "API-equivalent (subscription: no marginal $), price table version test-1" in line


def test_mixed_role_sums_only_the_priced_calls(tmp_path):
    unknown = {**CODEX, "model": "gpt-unknown", "models_used": ["gpt-unknown"]}
    eps = episodes(tmp_path, {"coder": [CODEX, unknown], "reviewer": [CLAUDE], "reviser": [CODEX]})
    m = compute_metrics(eps, table(tmp_path))
    assert m["overhead"]["coder_cost"] == {"cost_usd": CODEX_USD, "calls_priced": 1, "calls": 2}
    assert m["cost_by_role"]["coder"]["cost_sources"]["unpriced"] == 1
    assert "coder $0.0149 (1/2 calls priced)" in cost_line(render_summary(META, m))


def test_no_priced_call_is_not_reported_never_zero_dollars(tmp_path):
    eps = episodes(tmp_path, {"coder": [CODEX], "reviewer": [CLAUDE], "reviser": [CODEX]})
    m = compute_metrics(eps, PriceTable({}))  # no price table: Codex calls cannot be costed
    assert m["overhead"]["coder_cost"] == {"cost_usd": None, "calls_priced": 0, "calls": 2}
    assert m["cost_by_role"]["coder"]["cost_usd"] is None
    line = cost_line(render_summary(META, m))
    assert "coder not reported (0/2 calls priced)" in line and "$0.0000" not in line
    # the reviewer still has its CLI-reported cost; the reviser calls are unpriced
    assert "review + revision $0.0495 (2/4 calls priced)" in line


def test_claude_cross_check_compares_reported_and_estimated(tmp_path):
    eps = episodes(tmp_path, {"coder": [CODEX], "reviewer": [CLAUDE], "reviser": [CODEX]})
    m = compute_metrics(eps, table(tmp_path))
    assert m["cost_cross_check"] == {"calls": 2, "cli_reported_usd": 0.049504,
                                     "api_estimate_usd": 0.049504, "no_cache_split": 0,
                                     "gap_pct": 0.0}
    text = render_summary(META, m)
    assert ("Claude cross-check (2 calls with both figures): CLI-reported $0.0495 vs API "
            "estimate $0.0495 (estimate +0.0%)") in text

    # the same calls recorded without the 5m/1h split: estimated at the 5m rate, and it says so
    old = {**CLAUDE, "usage": {k: v for k, v in CLAUDE["usage"].items() if k != "cache_creation"}}
    eps = episodes(tmp_path / "old", {"coder": [CODEX], "reviewer": [old], "reviser": [CODEX]})
    m = compute_metrics(eps, table(tmp_path))
    assert m["cost_cross_check"]["gap_pct"] == -18.5 and m["cost_cross_check"]["no_cache_split"] == 2
    assert "2 of these calls recorded no 5m/1h cache-write split" in render_summary(META, m)

    # no call has both figures
    eps = episodes(tmp_path / "none", {"coder": [CODEX], "reviewer": [CODEX], "reviser": [CODEX]})
    assert "no call has both" in render_summary(META, compute_metrics(eps, table(tmp_path)))


def test_claude_usage_keeps_the_cache_write_split():
    result = {"type": "result", "total_cost_usd": 0.0247516, "modelUsage": {"claude-test": {}},
              "usage": {**CLAUDE["usage"], "service_tier": "standard"}}
    s = summarize_claude_events([result])
    assert s["usage"]["cache_creation"] == {"ephemeral_5m_input_tokens": 0,
                                            "ephemeral_1h_input_tokens": 3051}
