# normalize_username

Implement `normalize_username(raw: str) -> str` in `solution.py`.

Usernames must compare equal whenever a human would consider them the same, across all of Unicode:

- Apply Unicode NFKC normalization, so composed and decomposed forms (`"é"` vs `"e\u0301"`) and
  compatibility forms (fullwidth `"ＡＢＣ"`) normalize identically.
- Apply full Unicode case folding (not just lowercasing), so `"Straße"` and `"STRASSE"` normalize
  identically. The result must itself be NFKC-normalized.
- Strip leading/trailing whitespace (any Unicode whitespace) and replace every internal run of
  whitespace with a single underscore `_`.
- Raise `ValueError` if nothing remains.
