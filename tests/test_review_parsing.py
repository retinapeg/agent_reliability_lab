import json

import pytest

from agent_reliability.review.reviewer import FlagRule, MalformedReview, parse_review

F = {"severity": "high", "category": "unicode", "description": "d", "failing_input": "f('ß')",
     "expected": "'ss'", "confidence": 0.9}


def test_parse_and_flag():
    r = parse_review(json.dumps({"verdict": "request_changes", "findings": [F]}))
    assert r.flagged(FlagRule()) and r.findings[0].category == "unicode"


def test_fenced_json_accepted():
    assert parse_review("```json\n" + json.dumps({"verdict": "approve", "findings": []}) + "\n```")


def test_threshold_rule():
    low_conf = dict(F, confidence=0.5)
    low_sev = dict(F, severity="low")
    r = parse_review(json.dumps({"verdict": "request_changes", "findings": [low_conf, low_sev]}))
    assert not r.flagged(FlagRule())
    assert r.flagged(FlagRule(("high", "medium", "low"), 0.5))


def test_unknown_category_mapped_to_other():
    r = parse_review(json.dumps({"verdict": "request_changes", "findings": [dict(F, category="x")]}))
    assert r.findings[0].category == "other"


@pytest.mark.parametrize("text", [None, "", "looks good!", '{"verdict": "maybe", "findings": []}',
                                  '{"verdict": "approve"}',
                                  json.dumps({"verdict": "approve", "findings": [dict(F, confidence=2)]}),
                                  json.dumps({"verdict": "approve", "findings": [{"severity": "high"}]})])
def test_malformed_rejected(text):
    with pytest.raises(MalformedReview):
        parse_review(text)
