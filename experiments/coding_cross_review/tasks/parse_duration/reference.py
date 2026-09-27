import re

_PATTERN = re.compile(r"(?:([0-9]+)d)?(?:([0-9]+)h)?(?:([0-9]+)m)?(?:([0-9]+)s)?")


def parse_duration(text: str) -> int:
    match = _PATTERN.fullmatch(text)
    if not text or match is None or not any(match.groups()):
        raise ValueError(f"invalid duration: {text!r}")
    return sum(int(g or 0) * f for g, f in zip(match.groups(), (86400, 3600, 60, 1)))
