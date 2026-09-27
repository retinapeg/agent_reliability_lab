import pytest
from solution import format_cents


@pytest.mark.parametrize("cents,expected", [(-5, "-$0.05"), (0, "$0.00"), (-100, "-$1.00"),
                                            (5, "$0.05"), (123456789, "$1,234,567.89"),
                                            (-123456, "-$1,234.56")])
def test_values(cents, expected):
    assert format_cents(cents) == expected


@pytest.mark.parametrize("bad", [True, 1.5, "100"])
def test_rejects_non_int(bad):
    with pytest.raises(TypeError):
        format_cents(bad)
