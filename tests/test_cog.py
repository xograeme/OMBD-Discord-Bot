import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import discord
from discord import app_commands

from trivia.cog import TriviaCog, setup_trivia
from trivia.models import OmdbError, Question


QUESTION = Question("tt1375666", "Inception", "2010", "plot", "A thief enters dreams.")


class TestTriviaCog(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = SimpleNamespace(session=object())
        self.omdb = SimpleNamespace(fetch_question=AsyncMock(return_value=QUESTION))
        self.game = MagicMock()
        self.game.start.return_value = True
        self.game.submit_guess.return_value = None
        self.game.stop.return_value = None
        self.scores = SimpleNamespace(
            add_points=AsyncMock(return_value=25), top=AsyncMock(return_value=[])
        )
        self.cog = TriviaCog(self.bot, self.omdb, self.game, self.scores)
        self.channel = SimpleNamespace(id=22, send=AsyncMock())
        self.interaction = SimpleNamespace(
            guild_id=11, channel_id=22, channel=self.channel,
            response=SimpleNamespace(defer=AsyncMock(), send_message=AsyncMock()),
            followup=SimpleNamespace(send=AsyncMock()),
        )

    async def start(self, mode="plot"):
        await self.cog.start.callback(self.cog, self.interaction, mode)

    async def test_start_defers_before_fetch_and_posts_redacted_clue(self):
        async def fetch(mode):
            self.interaction.response.defer.assert_awaited_once()
            return QUESTION
        self.omdb.fetch_question.side_effect = fetch
        await self.start()
        self.game.start.assert_called_once_with(22, QUESTION, self.cog.on_timeout)
        call = self.interaction.followup.send.call_args
        self.assertEqual(call.kwargs["embed"].description, QUESTION.clue)
        self.assertNotIn(QUESTION.title, call.kwargs["embed"].description)
        self.assertIn("60 seconds", call.args[0])
        self.assertIn("10 points", call.args[0])

    async def test_cast_choice_awards_fifteen_points(self):
        cast = Question("tt1375666", "Inception", "2010", "cast", "Leonardo DiCaprio")
        self.omdb.fetch_question.return_value = cast
        await self.start("cast")
        self.omdb.fetch_question.assert_awaited_once_with("cast")
        self.assertIn("15 points", self.interaction.followup.send.call_args.args[0])

    async def test_omdb_error_is_friendly_and_releases_reservation(self):
        self.omdb.fetch_question.side_effect = OmdbError("private upstream detail")
        await self.start()
        self.game.start.assert_not_called()
        self.assertNotIn("private", self.interaction.followup.send.call_args.args[0])
        self.assertEqual(self.cog._pending, {})

    async def test_duplicate_start_does_not_fetch_another_question(self):
        await self.start()
        await self.start()
        self.omdb.fetch_question.assert_awaited_once()
        self.assertIn("already running", self.interaction.followup.send.call_args.args[0])

    async def test_simultaneous_start_reserves_channel_during_fetch(self):
        started, release = asyncio.Event(), asyncio.Event()
        async def fetch(mode):
            started.set()
            await release.wait()
            return QUESTION
        self.omdb.fetch_question.side_effect = fetch
        first = asyncio.create_task(self.start())
        await started.wait()
        await self.start()
        release.set()
        await first
        self.omdb.fetch_question.assert_awaited_once()
        self.game.start.assert_called_once()

    async def test_stop_during_fetch_cannot_start_a_round_afterwards(self):
        started, release = asyncio.Event(), asyncio.Event()
        async def fetch(mode):
            started.set()
            await release.wait()
            return QUESTION
        self.omdb.fetch_question.side_effect = fetch
        task = asyncio.create_task(self.start())
        await started.wait()
        await self.cog.stop.callback(self.cog, self.interaction)
        release.set()
        await task
        self.game.start.assert_not_called()
        self.assertEqual(self.cog._pending, {})

    async def test_failed_clue_send_cancels_round(self):
        self.interaction.followup.send.side_effect = RuntimeError("send failed")
        with self.assertRaises(RuntimeError):
            await self.start()
        self.game.stop.assert_called_once_with(22)
        self.assertEqual(self.cog._channels, {})

    async def test_leaderboard_is_per_guild_and_top_ten(self):
        self.scores.top.return_value = [(7, 25), (8, 10)]
        await self.cog.leaderboard.callback(self.cog, self.interaction)
        self.scores.top.assert_awaited_once_with(11, 10)
        self.assertIn("1. <@7> — 25 points", self.interaction.followup.send.call_args.args[0])

    async def test_stop_reveals_answer(self):
        self.game.stop.return_value = QUESTION
        await self.cog.stop.callback(self.cog, self.interaction)
        self.game.stop.assert_called_once_with(22)
        self.assertIn("Inception", self.interaction.response.send_message.call_args.args[0])
        self.assertIn("2010", self.interaction.response.send_message.call_args.args[0])

    async def test_win_scores_and_announces_total(self):
        self.game.submit_guess.return_value = QUESTION
        message = SimpleNamespace(
            author=SimpleNamespace(bot=False, id=7),
            guild=SimpleNamespace(id=11), channel=self.channel, content="Inception",
        )
        await self.cog.on_message(message)
        self.game.submit_guess.assert_called_once_with(22, 7, "Inception")
        self.scores.add_points.assert_awaited_once_with(11, 7, 10)
        announcement = self.channel.send.call_args.args[0]
        for text in ("<@7>", "Inception", "2010", "25"):
            self.assertIn(text, announcement)

    async def test_bots_and_direct_messages_are_ignored(self):
        for bot, guild in ((True, SimpleNamespace(id=11)), (False, None)):
            await self.cog.on_message(SimpleNamespace(author=SimpleNamespace(bot=bot), guild=guild))
        self.game.submit_guess.assert_not_called()

    async def test_timeout_reveals_answer_and_clears_channel(self):
        await self.start()
        await self.cog.on_timeout(22, QUESTION)
        self.assertIn("Inception", self.channel.send.call_args.args[0])
        self.assertIn("2010", self.channel.send.call_args.args[0])
        self.assertEqual(self.cog._channels, {})

    async def test_close_stops_active_rounds(self):
        await self.start()
        await self.cog.close()
        self.game.stop.assert_called_once_with(22)
        self.assertEqual(self.cog._channels, {})

    async def test_guild_commands_guard_direct_messages(self):
        self.interaction.guild_id = None
        for command in (self.cog.start, self.cog.leaderboard, self.cog.stop):
            await command.callback(self.cog, self.interaction)
        self.omdb.fetch_question.assert_not_awaited()
        self.scores.top.assert_not_awaited()
        self.game.stop.assert_not_called()

    async def test_setup_registers_real_commands_and_shared_dependencies(self):
        client = discord.Client(intents=discord.Intents.default())
        client.tree = app_commands.CommandTree(client)
        client.session = object()
        with patch("trivia.cog.Leaderboard") as leaderboard, patch.dict("os.environ", {"OMDB_API_KEY": "test-key"}):
            leaderboard.return_value.init = AsyncMock()
            cog = await setup_trivia(client)
        leaderboard.assert_called_once_with("trivia_scores.db")
        leaderboard.return_value.init.assert_awaited_once()
        self.assertIs(cog.omdb.session, client.session)
        group = client.tree.get_command("trivia")
        self.assertEqual({command.name for command in group.commands}, {"start", "leaderboard", "stop"})
        mode = group.get_command("start").parameters[0]
        self.assertEqual(mode.default, "plot")
        self.assertEqual({choice.value for choice in mode.choices}, {"plot", "cast"})
        self.assertTrue(all(command.binding is cog for command in group.commands))
        await client.close()


class TestEntrypointWiring(unittest.IsolatedAsyncioTestCase):
    async def test_actual_moviebot_setup_and_shutdown(self):
        # Execute only the real class definition: importing bot.py would load
        # private .env values and initialize the existing watchlist database.
        source = Path(__file__).resolve().parents[1] / "bot.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        definition = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "MovieBot")
        namespace = {
            "discord": discord, "app_commands": app_commands, "aiohttp": aiohttp,
            "JevClient": MagicMock(), "setup_trivia": AsyncMock(),
        }
        exec(compile(ast.Module(body=[definition], type_ignores=[]), str(source), "exec"), namespace)
        client = namespace["MovieBot"]()
        self.assertTrue(client.intents.message_content)
        cog = SimpleNamespace(close=AsyncMock())
        namespace["setup_trivia"].return_value = cog
        with patch.object(client.tree, "sync", new_callable=AsyncMock):
            try:
                await client.setup_hook()
                namespace["setup_trivia"].assert_awaited_once_with(client)
                self.assertIs(client.trivia, cog)
            finally:
                await client.close()
        cog.close.assert_awaited_once()

    async def test_existing_message_handler_forwards_to_trivia(self):
        source = Path(__file__).resolve().parents[1] / "bot.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        definition = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "on_message")
        definition.decorator_list = []
        trivia = SimpleNamespace(on_message=AsyncMock())
        bot = SimpleNamespace(trivia=trivia, user=object())
        namespace = {"discord": discord, "bot": bot}
        exec(compile(ast.Module(body=[definition], type_ignores=[]), str(source), "exec"), namespace)
        message = SimpleNamespace(author=SimpleNamespace(bot=False), guild=object(), mentions=[])
        await namespace["on_message"](message)
        trivia.on_message.assert_awaited_once_with(message)
