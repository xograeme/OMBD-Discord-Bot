import unittest

from trivia.matching import is_correct_guess


class TestMatching(unittest.TestCase):
    def test_normalizes_titles(self):
        examples = [
            ("  THE MATRIX  ", "The Matrix"),
            ("matrix", "The Matrix"),
            ("beautiful mind", "A Beautiful Mind"),
            ("unexpected journey", "An Unexpected Journey"),
            ("amelie", "Amélie"),
            ("pride and prejudice", "Pride & Prejudice"),
            ("wall-e", "WALL·E"),
            ("schindlers list", "Schindler's List"),
            ("Inception (2010)", "Inception"),
            ("The Matrix (1999)", "The Matrix"),
        ]
        for guess, title in examples:
            with self.subTest(guess=guess, title=title):
                self.assertTrue(is_correct_guess(guess, title))

    def test_accepts_small_typos(self):
        self.assertTrue(is_correct_guess("interstelar", "Interstellar"))
        self.assertTrue(is_correct_guess("inceptoin", "Inception"))

    def test_short_titles_require_exact_match(self):
        for guess, title in [("cocoo", "Coco"), ("its", "It"), ("upp", "Up"), ("dun", "Dune")]:
            with self.subTest(guess=guess, title=title):
                self.assertFalse(is_correct_guess(guess, title))
        self.assertTrue(is_correct_guess("UP (2009)", "Up"))
        self.assertTrue(is_correct_guess("the it", "It"))

    def test_rejects_empty_tiny_and_unrelated_guesses(self):
        for guess in ["", " ", "i", "!", "a", "the", "Batman", "not even close"]:
            with self.subTest(guess=guess):
                self.assertFalse(is_correct_guess(guess, "Inception"))

    def test_year_is_only_removed_at_the_end(self):
        self.assertFalse(is_correct_guess("(2010) Inception", "Inception"))
        self.assertFalse(is_correct_guess("Inception 2010", "Inception"))
