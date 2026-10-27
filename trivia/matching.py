"""Normalize movie titles and compare channel guesses."""

import re
import unicodedata
from difflib import SequenceMatcher


def _normalize(text: str) -> str:
    text = re.sub(r"\s*\(\s*\d{4}\s*\)\s*$", "", text)
    text = unicodedata.normalize("NFKD", text.casefold()).replace("&", " and ")
    text = "".join(
        char for char in text
        if not unicodedata.combining(char)
        and not unicodedata.category(char).startswith(("P", "S"))
    )
    text = " ".join(text.split())
    return re.sub(r"^(?:the|a|an)\s+", "", text)


def is_correct_guess(guess: str, title: str) -> bool:
    """Accept normalized titles and small typos, requiring exact short titles."""
    if len(guess.strip()) < 2:
        return False
    normalized_guess = _normalize(guess)
    normalized_title = _normalize(title)
    if len(normalized_guess) < 2 or not normalized_title:
        return False
    if len(normalized_title) <= 4:
        return normalized_guess == normalized_title
    return SequenceMatcher(None, normalized_guess, normalized_title).ratio() >= 0.88
