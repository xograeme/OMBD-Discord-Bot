"""Shared, frozen contract for the trivia minigame."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Question:
    imdb_id: str
    title: str
    year: str
    mode: Literal["plot", "cast"]
    clue: str


class OmdbError(Exception):
    """OMDb could not provide a usable trivia question."""


POINTS = {"plot": 10, "cast": 15}
ROUND_SECONDS = 60
