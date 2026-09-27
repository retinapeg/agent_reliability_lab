def median(values) -> float:
    if len(values) == 0:
        raise ValueError("empty")
    s = sorted(values)
    mid = len(s) // 2
    return float(s[mid]) if len(s) % 2 else (s[mid - 1] + s[mid]) / 2
