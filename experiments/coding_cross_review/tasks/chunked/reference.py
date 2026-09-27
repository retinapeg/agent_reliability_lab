def chunked(items, size: int) -> list[list]:
    if size < 1:
        raise ValueError("size must be >= 1")
    out: list[list] = []
    for item in items:
        if not out or len(out[-1]) == size:
            out.append([])
        out[-1].append(item)
    return out
