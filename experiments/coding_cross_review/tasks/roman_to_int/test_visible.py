from solution import roman_to_int


def test_three():
    assert roman_to_int("III") == 3


def test_nine():
    assert roman_to_int("IX") == 9


def test_fifty_eight():
    assert roman_to_int("LVIII") == 58
