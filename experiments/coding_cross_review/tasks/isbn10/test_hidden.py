from solution import is_valid_isbn10


def test_separators():
    assert is_valid_isbn10("0-306-40615-2") is True
    assert is_valid_isbn10("0 306 40615 2 ") is True


def test_lowercase_x():
    assert is_valid_isbn10("080442957x") is True


def test_x_not_last():
    assert is_valid_isbn10("X804429570") is False


def test_lengths():
    assert is_valid_isbn10("") is False
    assert is_valid_isbn10("03064061520") is False


def test_non_ascii_digits():
    assert is_valid_isbn10("\u0660\u0663\u0660\u0666\u0664\u0660\u0666\u0661\u0665\u0662") is False
