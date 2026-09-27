# chunked

Implement `chunked(items, size: int) -> list[list]` in `solution.py`.

- Split `items` into consecutive lists of length `size`; the last chunk may be shorter.
- `items` may be any iterable, including a one-shot generator.
- Return new lists; an empty input returns `[]`.
- Raise `ValueError` if `size < 1`.
