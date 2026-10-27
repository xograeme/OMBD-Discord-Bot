import asyncio
from pathlib import Path
import tempfile
import unittest

from trivia.leaderboard import Leaderboard


class TestLeaderboard(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db_path = str(Path(self.temp_dir.name) / "trivia.db")
        self.leaderboard = Leaderboard(self.db_path)
        await self.leaderboard.init()

    async def test_empty_scores(self):
        self.assertEqual(await self.leaderboard.get(1, 7), 0)
        self.assertEqual(await self.leaderboard.top(1), [])

    async def test_add_points_returns_accumulated_total(self):
        self.assertEqual(await self.leaderboard.add_points(1, 7, 10), 10)
        self.assertEqual(await self.leaderboard.add_points(1, 7, 15), 25)
        self.assertEqual(await self.leaderboard.get(1, 7), 25)

    async def test_scores_are_isolated_per_guild_and_user(self):
        await self.leaderboard.add_points(1, 7, 10)
        await self.leaderboard.add_points(2, 7, 15)
        await self.leaderboard.add_points(1, 8, 20)
        self.assertEqual(await self.leaderboard.get(1, 7), 10)
        self.assertEqual(await self.leaderboard.get(2, 7), 15)
        self.assertEqual(await self.leaderboard.top(1), [(8, 20), (7, 10)])

    async def test_top_is_descending_and_limited(self):
        for user_id in range(1, 13):
            await self.leaderboard.add_points(1, user_id, user_id * 10)
        self.assertEqual(
            await self.leaderboard.top(1),
            [(user_id, user_id * 10) for user_id in range(12, 2, -1)],
        )
        self.assertEqual(await self.leaderboard.top(1, 2), [(12, 120), (11, 110)])
        self.assertEqual(await self.leaderboard.top(1, 0), [])

    async def test_concurrent_upserts_have_no_lost_updates(self):
        other = Leaderboard(self.db_path)
        totals = await asyncio.gather(*(
            (self.leaderboard if index % 2 else other).add_points(1, 7, 10)
            for index in range(24)
        ))
        self.assertEqual(sorted(totals), list(range(10, 241, 10)))
        self.assertEqual(await self.leaderboard.get(1, 7), 240)

    async def test_reinitialization_preserves_persistent_scores(self):
        await self.leaderboard.add_points(1, 7, 15)
        reopened = Leaderboard(self.db_path)
        await reopened.init()
        self.assertEqual(await reopened.get(1, 7), 15)
        self.assertEqual(await reopened.top(1), [(7, 15)])
