"""Remove movie titles and distinctive title words from trivia clues."""

import re


_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "in", "into", "is", "it", "of", "on", "or", "the", "to", "was", "with",
})


def redact_title(text: str, title: str) -> str:
    """Redact a full title and its non-stopword words, without partial matches."""
    words = re.findall(r"[^\W_]+", title, flags=re.UNICODE)
    if not words:
        return text

    # A separator permits punctuation variants such as Spider-Man / Spider Man
    # and the colon or dash separating a title from its subtitle.
    full_title = r"[\W_]+".join(re.escape(word) for word in words)
    distinct_words = sorted(
        {word for word in words if len(word) >= 3 and word.casefold() not in _STOPWORDS},
        key=len,
        reverse=True,
    )
    alternatives = [full_title, *(re.escape(word) for word in distinct_words)]
    pattern = r"(?<!\w)(?:" + "|".join(alternatives) + r")(?!\w)"
    return re.sub(pattern, "[REDACTED]", text, flags=re.IGNORECASE)
