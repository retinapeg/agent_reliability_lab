from solution import is_valid_isbn10


def test_valid():
    assert is_valid_isbn10("0306406152") is True


def test_bad_checksum():
    assert is_valid_isbn10("0306406153") is False


def test_x_check():
    assert is_valid_isbn10("080442957X") is True
