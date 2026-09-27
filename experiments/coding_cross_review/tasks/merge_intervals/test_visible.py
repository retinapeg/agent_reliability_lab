from solution import merge_intervals


def test_overlap():
    assert merge_intervals([(1, 3), (2, 6), (8, 10)]) == [(1, 6), (8, 10)]


def test_single():
    assert merge_intervals([(1, 2)]) == [(1, 2)]


def test_gap_not_merged():
    assert merge_intervals([(1, 4), (5, 6)]) == [(1, 4), (5, 6)]
