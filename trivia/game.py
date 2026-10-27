"""In-memory rounds with one winner and one timer per channel."""

import asyncio
from collections.abc import Awaitable, Callable

from .matching import is_correct_guess
from .models import Question, ROUND_SECONDS


class GameManager:
    def __init__(self):
        self._rounds: dict[int, tuple[Question, asyncio.Task[None]]] = {}

    def start(
        self,
        channel_id: int,
        question: Question,
        on_timeout: Callable[[int, Question], Awaitable[None]],
    ) -> bool:
        """Start a round if this channel has none; call from the event loop."""
        if channel_id in self._rounds:
            return False
        task = asyncio.create_task(self._expire(channel_id, question, on_timeout))
        self._rounds[channel_id] = (question, task)
        return True

    def submit_guess(self, channel_id: int, user_id: int, text: str) -> Question | None:
        """Remove a correctly guessed round before another handler can win it."""
        active = self._rounds.get(channel_id)
        if active is None or not is_correct_guess(text, active[0].title):
            return None
        return self.stop(channel_id)

    def stop(self, channel_id: int) -> Question | None:
        active = self._rounds.pop(channel_id, None)
        if active is None:
            return None
        question, task = active
        task.cancel()
        return question

    async def _expire(
        self,
        channel_id: int,
        question: Question,
        on_timeout: Callable[[int, Question], Awaitable[None]],
    ) -> None:
        await asyncio.sleep(ROUND_SECONDS)
        active = self._rounds.get(channel_id)
        if active is not None and active[1] is asyncio.current_task():
            del self._rounds[channel_id]
            await on_timeout(channel_id, question)
