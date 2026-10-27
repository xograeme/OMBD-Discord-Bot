import asyncio
import re
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp

from trivia.models import OmdbError, Question
from trivia.movie_ids import MOVIE_IDS
from trivia.omdb import OmdbClient


def response_context(data):
    response = MagicMock()
    response.json = AsyncMock(return_value=data)
    context = AsyncMock()
    context.__aenter__.return_value = response
    return context


class TestOmdbClient(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.session = MagicMock()
        self.client = OmdbClient(self.session, "fake-test-key")
        self.data = {
            "Response": "True", "Title": "The Matrix", "Year": "1999",
            "Plot": "The Matrix follows a programmer into the matrix.",
            "Actors": "Keanu Reeves, Laurence Fishburne, Carrie-Anne Moss, Hugo Weaving, Joe Pantoliano",
        }

    async def test_plot_uses_https_params_shared_session_and_redacts(self):
        self.session.get.return_value = response_context(self.data)
        with patch("trivia.omdb.random.sample", return_value=["tt0133093"]):
            question = await self.client.fetch_question("plot")
        self.assertIsInstance(question, Question)
        self.assertEqual(question.imdb_id, "tt0133093")
        self.assertEqual(question.title, "The Matrix")
        self.assertEqual(question.year, "1999")
        self.assertEqual(question.mode, "plot")
        self.assertNotIn(question.title.casefold(), question.clue.casefold())
        self.assertNotIn("matrix", question.clue.casefold())
        args, kwargs = self.session.get.call_args
        self.assertEqual(args, ("https://www.omdbapi.com/",))
        self.assertEqual(kwargs["params"], {
            "apikey": "fake-test-key", "i": "tt0133093", "plot": "full",
        })
        self.assertEqual(kwargs["timeout"].total, 15)
        self.session.close.assert_not_called()

    async def test_cast_limits_to_four_and_redacts(self):
        self.data["Title"] = "Keanu Reeves"
        self.session.get.return_value = response_context(self.data)
        question = await self.client.fetch_question("cast")
        self.assertEqual(question.mode, "cast")
        self.assertEqual(len(question.clue.split(",")), 4)
        self.assertNotIn("Joe Pantoliano", question.clue)
        self.assertNotIn(question.title.casefold(), question.clue.casefold())

    async def test_false_and_unavailable_field_retry_different_ids(self):
        self.session.get.side_effect = [
            response_context({"Response": "False", "Error": "Movie not found!"}),
            response_context({**self.data, "Plot": "N/A"}),
            response_context(self.data),
        ]
        await self.client.fetch_question("plot")
        ids = [call.kwargs["params"]["i"] for call in self.session.get.call_args_list]
        self.assertEqual(len(ids), 3)
        self.assertEqual(len(set(ids)), 3)

    async def test_unusable_results_fail_after_three_requests(self):
        self.session.get.return_value = response_context({"Response": "False"})
        with self.assertRaises(OmdbError):
            await self.client.fetch_question("plot")
        self.assertEqual(self.session.get.call_count, 3)

    async def test_cast_na_retries(self):
        self.session.get.side_effect = [
            response_context({**self.data, "Actors": "N/A"}),
            response_context(self.data),
        ]
        await self.client.fetch_question("cast")
        self.assertEqual(self.session.get.call_count, 2)

    async def test_transport_and_json_errors_are_sanitized(self):
        for error in (aiohttp.ClientError("fake-test-key"), asyncio.TimeoutError(), ValueError("fake-test-key")):
            with self.subTest(error=type(error).__name__):
                self.session.get.reset_mock()
                self.session.get.side_effect = error
                with self.assertRaises(OmdbError) as caught:
                    await self.client.fetch_question("plot")
                self.assertNotIn("fake-test-key", str(caught.exception))
                self.assertIsNone(caught.exception.__context__)
                self.assertEqual(self.session.get.call_count, 3)

    async def test_invalid_mode_and_missing_key_do_not_request(self):
        with self.assertRaises(ValueError):
            await self.client.fetch_question("unknown")
        with self.assertRaises(OmdbError):
            await OmdbClient(self.session, "").fetch_question("plot")
        self.session.get.assert_not_called()

    async def test_malformed_payload_is_retried(self):
        for payload in ([], {**self.data, "Title": "N/A"}, {**self.data, "Plot": ""}):
            with self.subTest(payload=payload):
                self.session.get.side_effect = [response_context(payload), response_context(self.data)]
                self.assertIsInstance(await self.client.fetch_question("plot"), Question)

    def test_curated_ids_are_unique_and_valid(self):
        self.assertEqual(len(MOVIE_IDS), 100)
        self.assertEqual(len(set(MOVIE_IDS)), len(MOVIE_IDS))
        self.assertTrue(all(re.fullmatch(r"tt\d{7,8}", imdb_id) for imdb_id in MOVIE_IDS))


if __name__ == "__main__":
    unittest.main()
