# is_valid_isbn10

Implement `is_valid_isbn10(s: str) -> bool` in `solution.py`.

- Hyphens and spaces are separators and are ignored wherever they appear.
- After removing them there must be exactly 10 characters: nine ASCII digits `0-9`, then a check
  character that is an ASCII digit or `X`/`x` (meaning 10). `X` is only allowed in the last position.
- Valid when `sum((10 - i) * d_i for i in 0..9) % 11 == 0`.
- Never raise for string input; return `False` for anything invalid (including non-ASCII digits).
