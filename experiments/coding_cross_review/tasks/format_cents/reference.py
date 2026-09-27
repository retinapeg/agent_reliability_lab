def format_cents(cents: int) -> str:
    if type(cents) is not int:
        raise TypeError("cents must be an int")
    sign = "-" if cents < 0 else ""
    dollars, rest = divmod(abs(cents), 100)
    return f"{sign}${dollars:,}.{rest:02d}"
