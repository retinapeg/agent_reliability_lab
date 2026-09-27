from solution import chunked


def test_uneven():
    assert chunked([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]


def test_even():
    assert chunked([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]


def test_strings():
    assert chunked(["a", "b", "c"], 3) == [["a", "b", "c"]]
