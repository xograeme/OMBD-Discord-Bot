"""Slash commands and message handling for the movie trivia minigame."""

import os
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from .game import GameManager
from .leaderboard import Leaderboard
from .models import OmdbError, POINTS, Question, ROUND_SECONDS
from .omdb import OmdbClient


class TriviaCog(commands.Cog):
    trivia = app_commands.Group(name="trivia", description="Play movie trivia.")

    def __init__(self, bot, omdb: OmdbClient, game: GameManager, leaderboard: Leaderboard):
        self.bot = bot
        self.omdb = omdb
        self.game = game
        self.scores = leaderboard
        self._channels: dict[int, tuple[object, object]] = {}
        self._pending: dict[int, object] = {}

    @trivia.command(name="start", description="Guess a movie from its plot or cast.")
    @app_commands.guild_only()
    async def start(self, interaction: discord.Interaction, mode: Literal["plot", "cast"] = "plot"):
        if interaction.guild_id is None or interaction.channel is None:
            await interaction.response.send_message("Play trivia in a server channel.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        channel_id = interaction.channel_id
        if channel_id in self._channels or channel_id in self._pending:
            await interaction.followup.send("A trivia round is already running in this channel.")
            return

        reservation = object()
        self._pending[channel_id] = reservation
        try:
            try:
                question = await self.omdb.fetch_question(mode)
            except OmdbError:
                await interaction.followup.send("Couldn't load a movie right now. Please try again.")
                return
            if self._pending.get(channel_id) is not reservation:
                await interaction.followup.send("That trivia start was cancelled.")
                return
            if not self.game.start(channel_id, question, self.on_timeout):
                await interaction.followup.send("A trivia round is already running in this channel.")
                return
            self._channels[channel_id] = (reservation, interaction.channel)
            try:
                embed = discord.Embed(
                    title=f"Movie trivia: {mode}",
                    description=question.clue[:4096],
                    colour=discord.Colour.blurple(),
                )
                await interaction.followup.send(
                    f"Guess the movie title! You have {ROUND_SECONDS} seconds for {POINTS[mode]} points.",
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except BaseException:
                active = self._channels.get(channel_id)
                if active is not None and active[0] is reservation:
                    self.game.stop(channel_id)
                    self._channels.pop(channel_id, None)
                raise
        finally:
            if self._pending.get(channel_id) is reservation:
                self._pending.pop(channel_id)

    @trivia.command(name="leaderboard", description="Show this server's top ten trivia players.")
    @app_commands.guild_only()
    async def leaderboard(self, interaction: discord.Interaction):
        if interaction.guild_id is None:
            await interaction.response.send_message("Trivia scores belong to a server.", ephemeral=True)
            return
        await interaction.response.defer()
        scores = await self.scores.top(interaction.guild_id, 10)
        text = "\n".join(
            f"{rank}. <@{user_id}> — {points} points"
            for rank, (user_id, points) in enumerate(scores, 1)
        )
        await interaction.followup.send(
            "**Trivia leaderboard**\n" + (text or "No scores yet. Start a round with /trivia start!"),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @trivia.command(name="stop", description="End this channel's trivia round.")
    @app_commands.guild_only()
    async def stop(self, interaction: discord.Interaction):
        if interaction.guild_id is None:
            await interaction.response.send_message("Play trivia in a server channel.", ephemeral=True)
            return
        pending = self._pending.pop(interaction.channel_id, None)
        question = self.game.stop(interaction.channel_id)
        self._channels.pop(interaction.channel_id, None)
        if question is not None:
            text = f"Round stopped. The answer was {self._answer(question)}."
        elif pending is not None:
            text = "Trivia start cancelled."
        else:
            text = "There is no active trivia round in this channel."
        await interaction.response.send_message(text, allowed_mentions=discord.AllowedMentions.none())

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        question = self.game.submit_guess(message.channel.id, message.author.id, message.content)
        if question is None:
            return
        self._channels.pop(message.channel.id, None)
        points = POINTS[question.mode]
        total = await self.scores.add_points(message.guild.id, message.author.id, points)
        await message.channel.send(
            f"<@{message.author.id}> wins! The answer was {self._answer(question)}. "
            f"+{points} points; new total: {total}.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def on_timeout(self, channel_id: int, question: Question):
        active = self._channels.pop(channel_id, None)
        if active is not None:
            await active[1].send(
                f"Time's up! The answer was {self._answer(question)}.",
                allowed_mentions=discord.AllowedMentions.none(),
            )

    async def close(self):
        self._pending.clear()
        for channel_id in list(self._channels):
            self.game.stop(channel_id)
        self._channels.clear()

    @staticmethod
    def _answer(question: Question) -> str:
        return f"**{discord.utils.escape_markdown(question.title)}** ({question.year})"


async def setup_trivia(bot) -> TriviaCog:
    """Register with the existing discord.Client and reuse its HTTP session."""
    scores = Leaderboard("trivia_scores.db")
    await scores.init()
    cog = TriviaCog(bot, OmdbClient(bot.session, os.getenv("OMDB_API_KEY", "")), GameManager(), scores)
    bot.tree.add_command(cog.trivia)
    return cog
