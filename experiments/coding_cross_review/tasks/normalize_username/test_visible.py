from solution import normalize_username


def test_strips_and_lowercases():
    assert normalize_username("  Alice ") == "alice"


def test_internal_space():
    assert normalize_username("Bob Smith") == "bob_smith"


def test_upper():
    assert normalize_username("CAROL") == "carol"
