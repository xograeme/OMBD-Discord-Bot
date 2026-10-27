import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from trivia.game import GameManager
from trivia.models import Question


QUESTION = Question("tt1375666", "Inception", "2010", "plot", "A dream within a dream.")


class TestGameManager(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.game = GameManager()
        self.on_timeout = AsyncMock()

    async def asyncTearDown(self):
        tasks = [active[1] for active in self.game._rounds.values()]
        for channel_id in list(self.game._rounds):
            self.game.stop(channel_id)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def test_one_round_per_channel(self):
        self.assertTrue(self.game.start(1, QUESTION, self.on_timeout))
        self.assertFalse(self.game.start(1, QUESTION, self.on_timeout))
        self.assertTrue(self.game.start(2, QUESTION, self.on_timeout))
        self.assertIsNone(self.game.submit_guess(99, 5, "Inception"))
        self.assertIsNone(self.game.submit_guess(1, 5, "Batman"))
        self.assertEqual(self.game.submit_guess(2, 5, "Inception"), QUESTION)
        self.assertEqual(self.game.stop(1), QUESTION)

    async def test_simultaneous_correct_guesses_have_one_winner(self):
        self.game.start(1, QUESTION, self.on_timeout)

        async def guess(user_id):
            await asyncio.sleep(0)
            return self.game.submit_guess(1, user_id, "inception")

        results = await asyncio.gather(guess(101), guess(102))
        self.assertEqual(results.count(QUESTION), 1)
        self.assertEqual(results.count(None), 1)
        self.assertIsNone(self.game.submit_guess(1, 103, "inception"))
        self.on_timeout.assert_not_awaited()

    async def test_timeout_removes_round_then_reveals_answer(self):
        finished = asyncio.Event()

        async def on_timeout(channel_id, question):
            self.assertIsNone(self.game.submit_guess(channel_id, 1, "inception"))
            self.assertEqual((channel_id, question), (1, QUESTION))
            finished.set()

        with patch("trivia.game.ROUND_SECONDS", 0):
            self.game.start(1, QUESTION, on_timeout)
            await asyncio.wait_for(finished.wait(), 1)
        self.assertIsNone(self.game.stop(1))
        self.assertTrue(self.game.start(1, QUESTION, self.on_timeout))

    async def test_stop_cancels_timeout(self):
        self.game.start(1, QUESTION, self.on_timeout)
        task = self.game._rounds[1][1]
        await asyncio.sleep(0)
        self.assertEqual(self.game.stop(1), QUESTION)
        await asyncio.gather(task, return_exceptions=True)
        self.assertTrue(task.cancelled())
        self.assertIsNone(self.game.stop(1))
        self.on_timeout.assert_not_awaited()

    async def test_win_cancels_timeout(self):
        self.game.start(1, QUESTION, self.on_timeout)
        task = self.game._rounds[1][1]
        await asyncio.sleep(0)
        self.assertEqual(self.game.submit_guess(1, 5, "Inception (2010)"), QUESTION)
        await asyncio.gather(task, return_exceptions=True)
        self.assertTrue(task.cancelled())
        self.on_timeout.assert_not_awaited()

    async def test_stopped_timer_cannot_remove_replacement_round(self):
        self.game.start(1, QUESTION, self.on_timeout)
        old_task = self.game._rounds[1][1]
        self.game.stop(1)
        replacement = Question("tt0133093", "The Matrix", "1999", "cast", "Keanu Reeves")
        self.assertTrue(self.game.start(1, replacement, self.on_timeout))
        await asyncio.gather(old_task, return_exceptions=True)
        self.assertEqual(self.game.submit_guess(1, 5, "Matrix"), replacement)
        self.on_timeout.assert_not_awaited()
