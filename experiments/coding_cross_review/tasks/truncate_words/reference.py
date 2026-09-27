import re


def truncate_words(text: str, limit: int) -> str:
    if limit < 1:
        raise ValueError("limit must be >= 1")
    if len(text) <= limit:
        return text
    best = None
    for match in re.finditer(r"\S+", text):
        if match.end() + 1 <= limit:
            best = match.end()
        else:
            break
    if best is None:
        return text.lstrip()[: limit - 1] + "\u2026"
    return text[:best] + "\u2026"
