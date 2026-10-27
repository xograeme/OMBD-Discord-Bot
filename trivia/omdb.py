"""Fetch already-redacted trivia questions through a shared HTTP session."""

import asyncio
import random
from typing import Literal

import aiohttp

from .models import OmdbError, Question
from .movie_ids import MOVIE_IDS
from .redact import redact_title


class OmdbClient:
    def __init__(self, session: aiohttp.ClientSession, api_key: str):
        self.session = session
        self.api_key = api_key

    async def fetch_question(self, mode: Literal["plot", "cast"]) -> Question:
        if mode not in ("plot", "cast"):
            raise ValueError("Trivia mode must be plot or cast.")
        if not self.api_key:
            raise OmdbError("OMDb is not configured.")

        field = "Plot" if mode == "plot" else "Actors"
        for imdb_id in random.sample(MOVIE_IDS, min(3, len(MOVIE_IDS))):
            try:
                async with self.session.get(
                    "https://www.omdbapi.com/",
                    params={"apikey": self.api_key, "i": imdb_id, "plot": "full"},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as response:
                    response.raise_for_status()
                    data = await response.json()
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                continue

            if not isinstance(data, dict) or data.get("Response") != "True":
                continue
            title = data.get("Title")
            clue = data.get(field)
            if not isinstance(title, str) or title.strip() in ("", "N/A"):
                continue
            if not isinstance(clue, str) or clue.strip() in ("", "N/A"):
                continue
            if mode == "cast":
                actors = [actor.strip() for actor in clue.split(",") if actor.strip()]
                clue = ", ".join(actors[:4])
            return Question(
                imdb_id=imdb_id,
                title=title.strip(),
                year=str(data.get("Year", "N/A")),
                mode=mode,
                clue=redact_title(clue.strip(), title.strip()),
            )

        # Do not include upstream error messages or exception URLs: they may
        # contain the API key supplied as a query parameter.
        raise OmdbError("Couldn't find a trivia question. Please try again.")
