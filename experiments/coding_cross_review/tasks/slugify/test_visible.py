from solution import slugify


def test_basic():
    assert slugify("Hello World") == "hello-world"


def test_punctuation():
    assert slugify("Python 3.11 released") == "python-3-11-released"


def test_already_slug():
    assert slugify("already-slug") == "already-slug"
