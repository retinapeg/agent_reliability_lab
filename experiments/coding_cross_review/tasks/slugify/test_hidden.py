from solution import slugify


def test_accents():
    assert slugify("Café Crème") == "cafe-creme"
    assert slugify("Ünïcödé 2026!") == "unicode-2026"


def test_ligature():
    assert slugify("\ufb01le") == "file"


def test_edges_and_underscore():
    assert slugify("  --Hello--  ") == "hello"
    assert slugify("a_b") == "a-b"


def test_non_latin_dropped():
    assert slugify("日本語") == ""
    assert slugify("x 日本 y") == "x-y"
