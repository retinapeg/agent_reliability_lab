# parse_duration

Implement `parse_duration(text: str) -> int` in `solution.py`, returning a number of seconds.

- The input is one or more components `<number><unit>` with no spaces, where unit is one of
  `d` (86400 s), `h` (3600 s), `m` (60 s), `s` (1 s), lowercase only.
- Numbers are one or more ASCII digits `0-9` (leading zeros allowed, no sign). Values may exceed the
  natural range (`"90m"` is valid).
- Units must appear in strictly descending order (`d`, `h`, `m`, `s`) and each at most once.
- Raise `ValueError` for anything else: empty string, surrounding whitespace, repeated or
  out-of-order units, missing numbers, signs, uppercase units, or non-ASCII digits.
