import pytest
from solution import parse_duration


def test_all_units():
    assert parse_duration("1d2h3m4s") == 93784


def test_overflowing_component_and_zero():
    assert parse_duration("90m") == 5400
    assert parse_duration("0s") == 0


@pytest.mark.parametrize("bad", ["", "h", "1h1h", "1m1h", "1H", "-1s", " 1s", "1s ", "1h 30m",
                                 "\u0661s", "1.5h"])
def test_rejects_invalid(bad):
    with pytest.raises(ValueError):
        parse_duration(bad)
