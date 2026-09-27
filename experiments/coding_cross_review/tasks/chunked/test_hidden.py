import pytest
from solution import chunked


def test_generator_input():
    assert chunked((i for i in range(5)), 2) == [[0, 1], [2, 3], [4]]


def test_empty():
    assert chunked([], 3) == []


def test_size_larger_than_input():
    assert chunked([1, 2], 10) == [[1, 2]]


@pytest.mark.parametrize("size", [0, -1])
def test_invalid_size(size):
    with pytest.raises(ValueError):
        chunked([1, 2], size)
