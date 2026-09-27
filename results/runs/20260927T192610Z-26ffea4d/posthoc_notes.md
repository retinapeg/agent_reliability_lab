# Post-hoc notes — run `20260927T192610Z-26ffea4d`

Written after the run by the experimenter's coding assistant (Claude), by reading `episodes.jsonl`
and the raw traces. **None of this changes the predeclared metrics** in `metrics.json` /
`results/latest_summary.md`. Tasks, tests, flag rule and config were not modified after the run
(`protocol_audit.json`: task-file and config hashes match `run.json`). These are not human labels.

## Finding-level reading of the three flags

| task | hidden tests | review finding (abridged) | does the finding describe the hidden-test failure? |
|---|---|---|---|
| `truncate_words` | fail `test_multiple_spaces` | `split()` + `" ".join` discards the original whitespace, so the prefix and length check are wrong for text with runs of spaces; input `truncate_words('a  bb ccc', 5)` | yes: same defect |
| `word_frequencies` | fail `test_apostrophes` | `text.replace("'", "'")` is a no-op, so the typographic apostrophe `’` is never normalized and splits words; input `word_frequencies("don’t")` | yes: same defect |
| `roman_to_int` | pass | `re.match` with a `$` anchor accepts a trailing newline, so `roman_to_int('III\n')` raises `KeyError` instead of the `ValueError` the spec requires | not tested by the hidden suite (see below) |

## The "unconfirmed" roman_to_int flag reproduces

Executed post hoc in a subprocess, `roman_to_int('III\n')` raises `KeyError` with the original
candidate and `ValueError` with the revised candidate and with `reference.py`. The spec says "Raise
`ValueError` for anything else", so the flag describes a real spec violation that the hidden
tests do not cover. It stays **unconfirmed** in the metrics because the ground-truth rule was
fixed in advance to the hidden suite. It illustrates the documented limitation that hidden tests
are not exhaustive and that "unconfirmed" does not mean "false positive".

## The word_frequencies revision did not change the code

The revised `solution.py` is byte-identical to the original (`code_sha256` equal). The spec and the
coder/reviser prompts contain U+2019 (`’`). Neither Haiku output (coder, reviser) contains U+2019,
while the Sonnet reviewer output does, through the same CLI path. This points to model output, not
the harness or CLI dropping the character. Evidence, not proof.
