# format_cents

Implement `format_cents(cents: int) -> str` in `solution.py`, formatting an integer number of cents
as US dollars.

- Format: `$` then dollars with comma thousands separators, `.`, then exactly two cent digits,
  e.g. `123456` -> `"$1,234.56"`, `5` -> `"$0.05"`, `0` -> `"$0.00"`.
- Negative amounts put the sign before the dollar sign: `-5` -> `"-$0.05"`.
- Raise `TypeError` unless `cents` is an `int`; `bool` and `float` values are rejected.
