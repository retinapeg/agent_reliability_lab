# truncate_words

Implement `truncate_words(text: str, limit: int) -> str` in `solution.py`.

- If `len(text) <= limit`, return `text` unchanged.
- Otherwise return the longest prefix of `text` that ends at the end of a word (words are separated
  by whitespace), with trailing whitespace removed, followed by the single character `"…"`
  (U+2026). The total length including `"…"` must be `<= limit`.
- If not even the first word fits, cut the first word to `limit - 1` characters and append `"…"`.
- Lengths are counted in Python `str` characters. Raise `ValueError` if `limit < 1`.
