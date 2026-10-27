import unittest

from trivia.redact import redact_title


class TestRedactTitle(unittest.TestCase):
    def test_full_title_is_case_insensitive(self):
        self.assertEqual(
            redact_title("THE DARK KNIGHT returns. The knight falls.", "The Dark Knight"),
            "[REDACTED] returns. The [REDACTED] falls.",
        )

    def test_stopwords_and_partial_words_remain(self):
        self.assertEqual(
            redact_title("The matrix has a matrixed pattern in the city.", "The Matrix"),
            "[REDACTED] has a matrixed pattern in the city.",
        )

    def test_punctuation_subtitles_and_distinct_words(self):
        cases = [
            ("Spider-Man: Into the Spider-Verse", "Spider Man - Into the Spider Verse"),
            ("Mission: Impossible - Fallout", "mission impossible: fallout"),
            ("WALL-E", "WALL E"),
            ("Schindler's List", "SCHINDLER'S LIST"),
        ]
        for title, clue in cases:
            with self.subTest(title=title):
                result = redact_title(clue, title)
                self.assertEqual(result, "[REDACTED]")
                self.assertNotIn(title.casefold(), result.casefold())
        self.assertEqual(
            redact_title("Fallout follows an impossible mission.", "Mission: Impossible - Fallout"),
            "[REDACTED] follows an [REDACTED] [REDACTED].",
        )

    def test_short_titles_are_removed_in_full(self):
        for title in ("It", "Up", "Pi"):
            with self.subTest(title=title):
                self.assertEqual(redact_title(f"Watch {title}!", title), "Watch [REDACTED]!")

    def test_unicode_boundaries(self):
        self.assertEqual(
            redact_title("Amélie meets Amélies, not AMÉLIE.", "Amélie"),
            "[REDACTED] meets Amélies, not [REDACTED].",
        )

    def test_empty_title_leaves_text_unchanged(self):
        self.assertEqual(redact_title("A clue.", ""), "A clue.")


if __name__ == "__main__":
    unittest.main()
