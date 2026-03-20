from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


def _indian_grouping(number_text: str) -> str:
    if len(number_text) <= 3:
        return number_text

    last_three = number_text[-3:]
    remaining = number_text[:-3]
    groups = []

    while len(remaining) > 2:
        groups.insert(0, remaining[-2:])
        remaining = remaining[:-2]

    if remaining:
        groups.insert(0, remaining)

    return ",".join(groups + [last_three])


@register.filter
def rupees(value):
    if value in (None, ""):
        return "0"

    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return value

    sign = "-" if amount < 0 else ""
    amount = abs(amount)

    if amount == amount.to_integral():
        formatted = _indian_grouping(str(int(amount)))
    else:
        formatted = format(amount, ".2f").rstrip("0").rstrip(".")
        if "." in formatted:
            whole, fraction = formatted.split(".", 1)
            formatted = f"{_indian_grouping(whole)}.{fraction}"
        else:
            formatted = _indian_grouping(formatted)

    return f"{sign}{formatted}"
