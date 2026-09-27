# word_frequencies

Implement `word_frequencies(text: str) -> dict[str, int]` in `solution.py`.

- A word is a maximal run of Unicode letters or digits (any script, e.g. `"café"`, `"2026"`),
  which may contain single internal apostrophes between letters/digits (`"don't"`). Both `'` and
  the typographic `’` count as apostrophes; normalize them to `'` in the output.
- Apostrophes at the start or end of a word are not part of it. Underscores and all other
  characters are separators.
- Counting is case-insensitive using full Unicode case folding; keys are the case-folded words
  (`"Straße"` and `"STRASSE"` are the same word, key `"strasse"`).
