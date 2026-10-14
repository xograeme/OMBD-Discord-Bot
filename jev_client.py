import asyncio
import logging
import os
import re
import uuid

import aiohttp

log = logging.getLogger("jev")

# Genres the bot can recommend from (must match RECOMMENDED_MOVIES keys in bot.py)
GENRE_CRITERIA = {
    "any": "No specific genre is mentioned or implied.",
    "action": "Action: fights, explosions, chases, heroes.",
    "sci-fi": "Science fiction: space, future, technology, aliens.",
    "comedy": "Comedy: funny, light-hearted, makes you laugh.",
    "drama": "Drama: serious, emotional, character-driven stories.",
    "horror": "Horror: scary, creepy, frightening.",
    "animation": "Animation: animated, cartoon, anime, Pixar, Ghibli.",
    "thriller": "Thriller: suspense, tension, crime, psychological.",
    "romance": "Romance: love stories, date night, romantic.",
    "mystery": "Mystery: whodunit, detectives, solving a puzzle.",
    "fantasy": "Fantasy: magic, wizards, dragons, mythical worlds.",
    "documentary": "Documentary: real-life, true stories, nature, historical events.",
    "family": "Family: kids, wholesome, appropriate for children.",
    "adventure": "Adventure: exploration, quests, treasure hunting.",
    "crime": "Crime: gangsters, mafia, heist, true crime.",
    "anime": "Anime: Japanese animated movies or series, otaku culture.",
}

INTENT_CRITERIA = {
    "search": "Looking up info about a specific movie, franchise, or TV show.",
    "recommend": "Asking for a random suggestion or a good movie to watch.",
    "trailer": "Requesting a YouTube video link or trailer.",
    "watchlist_admin": "Managing the watchlists (adding, removing, viewing).",
    "actor": "Looking up info about an actor, actress, director, or cast member.",
    "casual": "General chatter, greetings, or unrelated questions.",
}

WATCHLIST_CRITERIA = {
    "view_server": "Wants to see the SHARED group list: 'our', 'the server', 'the group', 'everyone's', or just 'the watchlist'.",
    "view_personal": "Wants to see their OWN private list: 'my', 'mine', 'personal'.",
    "add": "Wants to add a specific movie or show to a watchlist.",
    "other": "Anything else, such as removing, clearing, or marking as watched.",
}


# Jev only classifies text; it can't return a movie title, so we pull it out with regex.
_REQUEST_PREFIX = re.compile(
    r"^(?:hey|yo|ok|okay|please|pls|um|"
    r"can you|could you|would you|will you|can i|could i|i want to|i wanna|i'd like to|let's|lets|"
    r"show me|give me|get me|find me|send me|pull up|look for|i want|i need|"
    r"tell me about|tell me|what about|how about|info on|info about|information on|information about|"
    r"look up|lookup|search for|search|details on|details for|details about|"
    r"what is|what's|whats|who directed|who stars in|who is in|who's in|is|"
    r"(?:the\s+)?(?:plot|cast|imdb rating|rating|ratings|director|runtime|reviews?)\s+(?:of|for|on))\b[\s,]*",
    re.IGNORECASE,
)


def extract_title(text: str) -> tuple[str, int | None]:
    """Best-effort extraction of a movie title (and optional year) from a chat message."""
    quoted = re.search(r'["\u201c](.+?)["\u201d]', text)
    if quoted:
        title = quoted.group(1)
    else:
        title = re.sub(r"[?!.]+\s*$", "", text).strip()

        add_match = re.search(
            r"\b(?:add|put|save|stick)\s+(.+?)\s+(?:to|on|in|into)\s+(?:my|our|the)?\s*"
            r"(?:server'?s?\s+|personal\s+|group\s+)?watch\s?list\b",
            title, re.IGNORECASE,
        )
        trailer_match = re.search(r"\btrailers?\s+(?:for|of|to)\s+(.+)", title, re.IGNORECASE)
        if add_match:
            title = add_match.group(1)
        elif trailer_match:
            title = trailer_match.group(1)
        else:
            title = re.sub(r"\s*\b(?:official\s+)?trailers?\b.*$", "", title, flags=re.IGNORECASE)

        previous = None
        while previous != title:
            previous = title
            title = _REQUEST_PREFIX.sub("", title).strip()

        title = re.sub(r"^(?:the\s+)?(?:movie|film|tv show|show|series)\s+", "", title, flags=re.IGNORECASE)
        title = re.sub(
            r"\s+(?:movie|film|please|pls|any good|good|worth watching)$", "", title, flags=re.IGNORECASE
        )

    year = None
    year_match = re.search(r"\s*\(?\b((?:19|20)\d{2})\)?$", title)
    if year_match and year_match.start() > 0:
        year = int(year_match.group(1))
        title = title[:year_match.start()]

    return title.strip(" ,:-\"'"), year


def extract_person(text: str) -> str | None:
    """Best-effort extraction of an actor or director name."""
    match = re.search(r"\b(?:with|starring|by|featuring|about|who is)\s+([A-Z][a-zA-Z-]+\s+[A-Z][a-zA-Z-]+)", text)
    if match:
        return match.group(1)
    
    match = re.search(r"\b(?:with|starring|by|featuring|about|who is)\s+([a-z-]+\s+[a-z-]+)", text, re.IGNORECASE)
    if match:
        name = match.group(1).title()
        if not re.search(r"\b(Movie|Film|Show|Series|Trailer|Watchlist|A|The|Some|Any)\b", name, re.IGNORECASE):
            return name
            
    return None


class JevClient:
    """Small async client for the FreeJev decisions API."""

    def __init__(self, session: aiohttp.ClientSession, timeout: float = 15.0):
        self.session = session
        self.api_key = os.getenv("TYPESAFE_API_KEY")
        self.endpoint = os.getenv("JEV_ENDPOINT", "https://freejev.org/api/v1/decisions")
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        # FreeJev allows only one running request per account, so queue calls
        self._lock = asyncio.Lock()

    async def decide(self, state: str, questions: dict) -> dict | None:
        """Send one decision request. Returns the 'answers' dict, or None on failure."""
        if not self.api_key:
            log.warning("No Jev API key found (TYPESAFE_API_KEY).")
            return None

        payload = {"state": state, "questions": questions}
        # FreeJev requires a unique Idempotency-Key for each intended run
        headers = {**self.headers, "Idempotency-Key": str(uuid.uuid4())}

        async with self._lock:
            try:
                async with self.session.post(self.endpoint, headers=headers, json=payload, timeout=self.timeout) as response:
                    if response.status != 200:
                        log.error(f"FreeJev API returned {response.status}: {await response.text()}")
                        return None
                    data = await response.json()
            except asyncio.TimeoutError:
                log.warning("FreeJev API timed out.")
                return None
            except Exception as e:
                log.error(f"FreeJev request error: {e}")
                return None

        answers = data.get("answers")
        if not isinstance(answers, dict):
            log.error(f"Unexpected JSON structure: {data}")
            return None
        return answers

    @staticmethod
    def _choice(answers: dict, key: str, allowed: dict, default: str) -> str:
        try:
            value = answers[key]["choice"]
        except (KeyError, TypeError):
            return default
        return value if value in allowed else default

    async def classify_intent(self, user_text: str) -> str:
        """Return just the intent label (kept for simple use/testing)."""
        return (await self.analyze(user_text))["intent"]

    async def analyze(self, user_text: str) -> dict:
        """Classify a message into intent, genre and watchlist action in one call."""
        questions = {
            "intent": {
                "type": "choice",
                "instructions": "Classify what the user wants the movie bot to do.",
                "criteria": INTENT_CRITERIA,
            },
            "genre": {
                "type": "choice",
                "instructions": "Which movie genre does the user ask for, if any?",
                "criteria": GENRE_CRITERIA,
            },
            "watchlist_action": {
                "type": "choice",
                "instructions": "If the user is talking about a watchlist, what do they want to do?",
                "criteria": WATCHLIST_CRITERIA,
            },
        }

        answers = await self.decide(user_text, questions) or {}
        return {
            "intent": self._choice(answers, "intent", INTENT_CRITERIA, "casual"),
            "genre": self._choice(answers, "genre", GENRE_CRITERIA, "any"),
            "watchlist_action": self._choice(answers, "watchlist_action", WATCHLIST_CRITERIA, "other"),
            "ok": bool(answers),
        }
