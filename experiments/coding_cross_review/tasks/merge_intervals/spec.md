# merge_intervals

Implement `merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]` in
`solution.py`.

- Intervals are closed `(start, end)`. Merge any that overlap **or touch** (`(1, 2)` and `(2, 3)`
  merge into `(1, 3)`).
- The input may be in any order. Return merged tuples sorted by start.
- Do not mutate the input list.
- Raise `ValueError` if any interval has `start > end`. An empty input returns `[]`.
