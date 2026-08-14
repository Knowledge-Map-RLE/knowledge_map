"""
Layer: Domain
Package: domain.rules.money
Responsibility: Работа с деньгами в копейках (int) и строковым форматом ЮKassa.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def format_amount(kopecks: int) -> str:
    """150000 копеек -> '1500.00' (формат ЮKassa)."""
    if kopecks < 0:
        raise ValueError("Amount must be non-negative")
    return f"{Decimal(kopecks) / 100:.2f}"


def value_to_kopecks(value: str) -> int:
    """'1500.00' -> 150000 копеек."""
    try:
        decimal = Decimal(value)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"Invalid money value: {value!r}")
    return int((decimal * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
