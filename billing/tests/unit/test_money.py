"""Тесты доменных правил работы с деньгами."""
import pytest

from domain.rules.money import format_amount, value_to_kopecks


@pytest.mark.parametrize(
    "kopecks,expected",
    [
        (0, "0.00"),
        (100, "1.00"),
        (150000, "1500.00"),
        (2000000, "20000.00"),
        (1, "0.01"),
        (199, "1.99"),
    ],
)
def test_format_amount(kopecks, expected):
    assert format_amount(kopecks) == expected


def test_format_amount_rejects_negative():
    with pytest.raises(ValueError):
        format_amount(-1)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("0.00", 0),
        ("1.00", 100),
        ("1500.00", 150000),
        ("20000.00", 2000000),
        ("0.01", 1),
        ("1.99", 199),
    ],
)
def test_value_to_kopecks(value, expected):
    assert value_to_kopecks(value) == expected


def test_value_to_kopecks_rounds_half_up():
    assert value_to_kopecks("1.005") == 101


@pytest.mark.parametrize("bad", ["abc", "", "1.2.3", None])
def test_value_to_kopecks_rejects_invalid(bad):
    with pytest.raises(ValueError):
        value_to_kopecks(bad)


def test_roundtrip():
    assert format_amount(value_to_kopecks("1234.56")) == "1234.56"
