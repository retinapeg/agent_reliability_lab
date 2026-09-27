from solution import truncate_words


def test_fits():
    assert truncate_words("short", 10) == "short"


def test_word_boundary():
    assert truncate_words("the quick brown fox", 12) == "the quick\u2026"


def test_two_words():
    assert truncate_words("hello world", 8) == "hello\u2026"
