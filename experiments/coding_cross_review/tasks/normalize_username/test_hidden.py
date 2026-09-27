import pytest
from solution import normalize_username


def test_casefold_eszett():
    assert normalize_username("Straße") == normalize_username("STRASSE") == "strasse"


def test_composed_equals_decomposed():
    assert normalize_username("Jose\u0301") == normalize_username("Jos\u00e9")


def test_fullwidth_compat():
    assert normalize_username("ＡＢＣ") == "abc"


def test_whitespace_runs_and_unicode_space():
    assert normalize_username("\u00a0a\t\n b\u2003") == "a_b"


def test_empty_raises():
    with pytest.raises(ValueError):
        normalize_username(" \t ")
