import pytest
from solution import truncate_words


def test_exact_fit_unchanged():
    assert truncate_words("hello world", 11) == "hello world"


def test_ellipsis_counts_toward_limit():
    assert truncate_words("hello world", 6) == "hello\u2026"
    assert len(truncate_words("the quick brown fox", 10)) <= 10


def test_first_word_too_long():
    assert truncate_words("hello world", 5) == "hell\u2026"
    assert truncate_words("hello", 1) == "\u2026"


def test_multiple_spaces():
    assert truncate_words("a  b  c", 4) == "a\u2026"


def test_invalid_limit():
    with pytest.raises(ValueError):
        truncate_words("abc", 0)
