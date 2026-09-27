import unicodedata


def normalize_username(raw: str) -> str:
    text = unicodedata.normalize("NFKC", unicodedata.normalize("NFKC", raw).casefold())
    parts = text.split()
    if not parts:
        raise ValueError("empty username")
    return "_".join(parts)
