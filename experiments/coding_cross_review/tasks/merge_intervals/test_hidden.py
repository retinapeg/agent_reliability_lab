import pytest
from solution import merge_intervals


def test_touching_merge():
    assert merge_intervals([(1, 2), (2, 3)]) == [(1, 3)]


def test_unsorted():
    assert merge_intervals([(8, 10), (1, 3), (2, 6)]) == [(1, 6), (8, 10)]


def test_nested():
    assert merge_intervals([(1, 10), (2, 3)]) == [(1, 10)]


def test_does_not_mutate():
    data = [(5, 6), (1, 2)]
    merge_intervals(data)
    assert data == [(5, 6), (1, 2)]


def test_empty_and_point():
    assert merge_intervals([]) == []
    assert merge_intervals([(5, 5)]) == [(5, 5)]


def test_invalid():
    with pytest.raises(ValueError):
        merge_intervals([(3, 1)])
