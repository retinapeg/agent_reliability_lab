from solution import word_frequencies


def test_repeats():
    assert word_frequencies("the cat the hat") == {"the": 2, "cat": 1, "hat": 1}


def test_case_and_punctuation():
    assert word_frequencies("Hello, hello!") == {"hello": 2}


def test_distinct():
    assert word_frequencies("one two three") == {"one": 1, "two": 1, "three": 1}
