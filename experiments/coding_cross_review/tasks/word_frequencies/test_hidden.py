from solution import word_frequencies


def test_unicode_letters():
    assert word_frequencies("Café café CAFÉ") == {"café": 3}


def test_casefold():
    assert word_frequencies("Straße STRASSE") == {"strasse": 2}


def test_apostrophes():
    assert word_frequencies("don't Don\u2019t") == {"don't": 2}
    assert word_frequencies("'quoted'") == {"quoted": 1}


def test_underscore_and_digits():
    assert word_frequencies("a_b 2026 2026") == {"a": 1, "b": 1, "2026": 2}


def test_empty():
    assert word_frequencies("") == {}
