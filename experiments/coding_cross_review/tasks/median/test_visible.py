from solution import median


def test_odd_unsorted():
    assert median([1, 3, 2]) == 2


def test_single():
    assert median([5]) == 5


def test_sorted_odd():
    assert median([1, 2, 3, 4, 5]) == 3
