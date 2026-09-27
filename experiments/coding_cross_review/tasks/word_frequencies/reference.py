import re
from collections import Counter

_WORD = re.compile(r"[^\W_]+(?:'[^\W_]+)*")


def word_frequencies(text: str) -> dict[str, int]:
    return dict(Counter(w.casefold() for w in _WORD.findall(text.replace("\u2019", "'"))))
