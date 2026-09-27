# slugify

Implement `slugify(title: str) -> str` in `solution.py`.

- Apply Unicode NFKD normalization and drop combining marks, so `"Café"` becomes `"cafe"` and
  the ligature `"ﬁ"` becomes `"fi"`.
- Lowercase the result.
- Replace every run of characters that are not ASCII letters `a-z` or digits `0-9` with a single `-`
  (so underscores, punctuation and letters without an ASCII decomposition are separators).
- Strip leading and trailing `-`. Return `""` if nothing remains.
