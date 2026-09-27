import pytest
from solution import roman_to_int


def test_large():
    assert roman_to_int("MCMXCIV") == 1994
    assert roman_to_int("MMMCMXCIX") == 3999


@pytest.mark.parametrize("bad", ["IIII", "VV", "IC", "VX", "MMMM", "", "iv", "IIV", "XM"])
def test_rejects_non_canonical(bad):
    with pytest.raises(ValueError):
        roman_to_int(bad)
