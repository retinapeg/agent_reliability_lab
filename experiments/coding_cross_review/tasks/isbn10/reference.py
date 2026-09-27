def is_valid_isbn10(s: str) -> bool:
    chars = s.replace("-", "").replace(" ", "")
    if len(chars) != 10:
        return False
    digits = []
    for i, c in enumerate(chars):
        if c in "0123456789":
            digits.append(int(c))
        elif i == 9 and c in "Xx":
            digits.append(10)
        else:
            return False
    return sum((10 - i) * d for i, d in enumerate(digits)) % 11 == 0
