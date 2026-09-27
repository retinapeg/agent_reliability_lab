from solution import camel_to_snake


def test_camel():
    assert camel_to_snake("camelCase") == "camel_case"


def test_pascal():
    assert camel_to_snake("CamelCase") == "camel_case"


def test_simple():
    assert camel_to_snake("simple") == "simple"
