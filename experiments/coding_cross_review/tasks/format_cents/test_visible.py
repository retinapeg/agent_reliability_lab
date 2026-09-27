from solution import format_cents


def test_thousands():
    assert format_cents(123456) == "$1,234.56"


def test_whole_dollar():
    assert format_cents(100) == "$1.00"


def test_under_dollar():
    assert format_cents(99) == "$0.99"
