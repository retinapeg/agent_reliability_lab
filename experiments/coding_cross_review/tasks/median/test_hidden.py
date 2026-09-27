import pytest
from solution import median


def test_even():
    assert median([1, 2, 3, 4]) == 2.5
    assert median([4, 1, 3, 2]) == 2.5


def test_negative_even():
    assert median([-5, -1]) == -3.0


def test_returns_float():
    assert isinstance(median([1, 3, 2]), float)


def test_no_mutation():
    data = [3, 1, 2]
    median(data)
    assert data == [3, 1, 2]


def test_tuple_input():
    assert median((9, 1, 5)) == 5.0


def test_empty():
    with pytest.raises(ValueError):
        median([])
